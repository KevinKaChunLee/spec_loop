# 音频路由与提示音（audio-control-manager）Specification

## Purpose
描述 `telephony_call_manager/services/audio/` 的音频管理：`AudioControlManager`（总控，`CallStateListenerBase` 派生）、`AudioDeviceManager`（设备路由状态机）、`CallStateProcessor`/`AudioSceneProcessor`（呼叫状态机与 `audio_state/` 下 14 个状态类）、`Ring`/`Sound`/`Tone`/`AudioPlayer`（铃声/彩振/提示音/文件播放）、`AudioProxy`（音频系统 API 封装）。编译开关：`SUPPORT_VIBRATOR`（`audio_proxy.cpp` 振动，sensors_miscdevice 部件在位时开）、`ABILITY_AUDIO_SUPPORT`（`tone.cpp` 分支，调用不存在的 `AudioProxy::GetToneDescriptorPath`，宏打开即编译失败，属遗留死代码，基线不开启）。

## Requirements

### Requirement: 呼叫状态驱动的音频场景机
系统 SHALL 由 `AudioControlManager::CallStateUpdated` 将 TelCallState 经 `HandleNextState`/`HandlePriorState` 翻译为 `NEW_DIALING_CALL/NEW_ALERTING_CALL/NEW_INCOMING_CALL/NEW_ACTIVE_CS_CALL/NEW_ACTIVE_IMS_CALL/NEW_ACTIVE_OTT_CALL` 与 `NO_MORE_*` 系列 `AudioEvent`，交 `AudioSceneProcessor::ProcessEvent`（提交 `ffrt::queue "report_audio_state_change"` 异步串行）按 `memberFuncMap_` 分发 `SwitchDialing/SwitchAlerting/SwitchIncoming/SwitchCS/SwitchIMS/SwitchHolding/SwitchInactive` 与 14 个 `audio_state/` 状态类（`InActiveState/DialingState/AlertingState/IncomingState/CSCallState/IMSCallState/HoldingState/OTTCallState` 与 `InactiveDeviceState/SpeakerDeviceState/EarpieceDeviceState/WiredHeadsetDeviceState/BluetoothDeviceState`）。
#### Scenario: 场景优先级仲裁
- **WHEN** 多状态通话并存时 `CallStateProcessor::UpdateCurrentCallState` 仲裁
- **THEN** 按 active > holding > incoming > dialing > alerting > inactive 的优先级产出唯一 `SWITCH_*` 事件

#### Scenario: 最后一通结束播结束音
- **WHEN** `NO_MORE_ACTIVE_CALL/NO_MORE_ALERTING_CALL` 到达且 `ShouldStopSoundtone()` 为真
- **THEN** `StopRingback` 并按需 `PlayCallEndedTone(CALL_ENDED_NORMALLY)`（`TONE_FINISHED`，播放 `CALL_ENDED_PLAY_TIME = 300` 毫秒）

### Requirement: 铃声播放
系统 SHALL 由 `AudioControlManager::PlayRingtone` 在 `ShouldPlayRingtone()`（无 ALERTING 呼叫、存在 INCOMING、当前非 RINGING、非 CRS SOUNDING）通过后：CRS 来电（`GetCrsType() == CRS_TYPE`）走 `dealCrsScene(ringMode)`（VIBRATE 走 `StartVibrator`；NORMAL 或 `IsBtOrWireHeadPlugin` 走 `PlaySoundtone` + `AdjustVolumesForCrs`）；视频彩振（`CallObjectManager::IsVideoRing(...)`）只振动不发声；否则 `ring_->Play(accountId, ringtonePath, HapticStartupMode)`（蓝牙通话 `FAST`，其余 `DEFAULT`），成功后 `PostProcessRingtone` 补静音（读 `isNeedMuteRing`）。
#### Scenario: 接听时铃声未起补静音
- **WHEN** `MuteRinger()` 时铃声尚未启动
- **THEN** 向来电 `WantParams` 写 `isNeedMuteRing = 1`（`AAFwk::Integer::Box`），铃声后启动时被 `PostProcessRingtone` 补静音

#### Scenario: 静音铃响时 CRS 停网络彩振
- **WHEN** CRS 来电（`GetCrsType() == CRS_TYPE`）时静音铃响
- **THEN** `MuteNetWorkRingTone(true)` 停止网络彩振播放并 `SendMuteRingEvent()` 发 `EVENT_MUTE_RING`

### Requirement: 回铃音与等待音
系统 SHALL 由 `PlayRingback/StopRingback`、`PlayWaitingTone/StopWaitingTone` 走 `PlayCallTone/StopCallTone`（`toneStateLock_` 递归互斥锁保护 `toneState_`）；`PlayRingback` 受 `SetLocalRingbackNeeded` 设置的 `isLocalRingbackNeeded_` 控制（true→false 时自动 `StopRingback`）；DTMF 走 `PlayDtmfTone(char)`（`Tone::ConvertDigitToTone` 后播放 `DTMF_PLAY_TIME = 30` 毫秒）。
#### Scenario: 本地回铃音开关
- **WHEN** 协议栈侧设置 `SetLocalRingbackNeeded(false)` 且本地回铃音正在播放
- **THEN** 本地 `StopRingback` 立即执行

### Requirement: 音频设备路由
系统 SHALL 由 `AudioControlManager::GetInitAudioDeviceType()` 固化设备优先级：分布式汽车（`IsDistributedCallConnected`）> 星闪（`IsNearlinkActived`）> 蓝牙 SCO（`IsBtActived`）> 有线耳机（`IsWiredHeadsetConnected`）> 助听器（`IsBtHearingAidActived`）> 前台视频/卫星/蓝牙通话强制 `DEVICE_SPEAKER` > `IsEarpieceAvailable` 的 `DEVICE_EARPIECE` > `DEVICE_SPEAKER`；`AudioDeviceManager::SwitchDevice(AudioDeviceType)` 分派 `EnableEarpiece/EnableSpeaker/EnableWiredHeadset/EnableBtSco/EnableNearlink/EnableBtHearingAid/DisableAll` 并经 `AudioProxy::SetEarpieceDevActive/SetSpeakerDevActive/SetWiredHeadsetDevActive/SetBluetoothDevActive` 激活后 `SetCurrentAudioDevice` + `ReportAudioDeviceChange`。
#### Scenario: 有线耳机拔出重路由
- **WHEN** `AudioDeviceChangeCallback::OnDeviceChange` 收到有线耳机移除
- **THEN** `RemoveAudioDeviceList` + `AddEarpiece` 回补听筒并触发 `WIRED_HEADSET_DISCONNECTED`→`InitAudioDevice` 重路由

#### Scenario: 蓝牙通话暂时排除 SCO
- **WHEN** 蓝牙通话进入拨号/来电视景
- **THEN** `ExcludeBluetoothSco` 以 `AudioSystemManager::ExcludeOutputDevices` 暂时排除 SCO 输出（`isScoTemporarilyDisabled_`），进入 `SwitchInactive` 时 `UnexcludeBluetoothSco` 恢复

### Requirement: 麦克风静音
系统 SHALL 由 `AudioControlManager::SetMute(bool)` 在紧急呼叫时强制不静音；`TYPE_BLUETOOTH` 活动通话走 `AudioSystemManager::SetExtraParameters("hfp_extra", {"hfp_set_mic_mute", strMute})`，其余走 `AudioProxy::SetMicrophoneMute`；随后 `ReportAudioDeviceInfo` 与 `SetMicPhoneState`。
#### Scenario: 蓝牙通话静音走专用通道
- **WHEN** 蓝牙通话中用户开启静音
- **THEN** 静音经 `hfp_extra` 参数下发，设备变化信息同步上报

### Requirement: 语音↔视频切换联动
系统 SHALL 由 `AudioControlManager::VideoStateUpdated`（仅 `TYPE_IMS/TYPE_BLUETOOTH`）经 `CheckTypeAndSetAudioDevice`：语音→视频切扬声器（`IsExternalAudioDevice` 含分布式汽车则保留），视频→语音（非 sink、非用户设置）回 `DEVICE_EARPIECE`；接听 CRS 后 500 毫秒（`UNMUTE_SOUNDTONE_DELAY_TIME = 500000` 微秒）`UnmuteSoundTone` 恢复网络彩振音量（`RestoreVoiceValumeIfNecessary` 取回 `GetBackupVoiceVolume`）。
#### Scenario: 升级为视频通话
- **WHEN** IMS 通话由语音升级为视频
- **THEN** 音频输出切换到扬声器（外接大屏/分布式汽车设备除外）

### Requirement: 视频彩振振动
系统 SHALL 在视频彩振场景（`NeedPlayVideoRing`：OsAccount 已解锁、非 CRS、`IsNotWearOnWrist`、`IsSystemVideoRing`（`SystemSoundManager::GetCurrentRingtoneAttribute` 为 `MEDIA_TYPE_VID`，兜底 `SYSTEM_VIDEO_RING = "system_video_ring"`））只 `StartVibrator` 振动（`SUPPORT_VIBRATOR` 下经 `Sensors::StartVibrator("haptic.ringtone.Dream_It_Possible")` 并以 2 秒循环重触发），挂断/接听时 `StopVibrator`。
#### Scenario: 系统视频彩振来电
- **WHEN** 来电设置的系统铃音为视频彩振且振动器部件在位
- **THEN** 来电不播铃声仅振动，通话结束时停止振动

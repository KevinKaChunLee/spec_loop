# Spec Delta

## MODIFIED Requirements

### Requirement: 呼叫状态驱动的音频场景机
系统 SHALL 由 `AudioControlManager::CallStateUpdated` 将 TelCallState 经 `HandleNextState`/`HandlePriorState` 翻译为 `NEW_DIALING_CALL/NEW_ALERTING_CALL/NEW_INCOMING_CALL/NEW_ACTIVE_CS_CALL/NEW_ACTIVE_IMS_CALL` 与 `NO_MORE_*` 系列 `AudioEvent`（OTT 事件不迁移），交 `AudioSceneProcessor::ProcessEvent`（打桩 `EventHandler` 队列异步串行，替代 `ffrt::queue "report_audio_state_change"`）按 `memberFuncMap_` 分发 `SwitchDialing/SwitchAlerting/SwitchIncoming/SwitchCS/SwitchIMS/SwitchHolding/SwitchInactive` 与收敛后的状态类（`InActiveState/DialingState/AlertingState/IncomingState/CSCallState/IMSCallState/HoldingState` 与 `InactiveDeviceState/SpeakerDeviceState/EarpieceDeviceState`；`OTTCallState/WiredHeadsetDeviceState/BluetoothDeviceState` 不迁移）。
#### Scenario: 场景优先级仲裁
- **WHEN** 多状态通话并存时 `CallStateProcessor::UpdateCurrentCallState` 仲裁
- **THEN** 按 active > holding > incoming > dialing > alerting > inactive 的优先级产出唯一 `SWITCH_*` 事件

#### Scenario: 最后一通结束播结束音
- **WHEN** `NO_MORE_ACTIVE_CALL/NO_MORE_ALERTING_CALL` 到达且 `ShouldStopSoundtone()` 为真
- **THEN** `StopRingback` 并按需 `PlayCallEndedTone(CALL_ENDED_NORMALLY)`（`TONE_FINISHED`，播放 `CALL_ENDED_PLAY_TIME = 300` 毫秒；音频 API 调用点以 `// todo!!! [audio]` 占位，`toneState_` 记录照常推进）

### Requirement: 铃声播放
系统 SHALL 由 `AudioControlManager::PlayRingtone` 在 `ShouldPlayRingtone()`（无 ALERTING 呼叫、存在 INCOMING、当前非 RINGING）通过后执行 `ring_->Play(accountId, ringtonePath, HapticStartupMode)`（音频系统 API 调用点以 `// todo!!! [audio]` 占位，铃声状态照常记录；蓝牙通话 `FAST` 模式分支不迁移，统一 `DEFAULT` 形态），成功后 `PostProcessRingtone` 补静音（读 `isNeedMuteRing` 标志，标志改经结构体传递替代 `WantParams`）；CRS 分支（`GetCrsType() == CRS_TYPE` 视频彩振）与振动（`SUPPORT_VIBRATOR`）不迁移。
#### Scenario: 接听时铃声未起补静音
- **WHEN** `MuteRinger()` 时铃声尚未启动
- **THEN** 补静音标志（结构体形态）置位，铃声后启动时被 `PostProcessRingtone` 补静音

#### Scenario: 静音铃响时 CRS 停网络彩振
- **WHEN** `MuteRinger()` 于任一来电执行（CRS 分支已移除）
- **THEN** 不存在 `MuteNetWorkRingTone` 停播链路（视频彩振不支持），静音铃响与补静音标志逻辑照常执行

#### Scenario: 普通来电振铃占位
- **WHEN** 普通来电进入振铃触发 `PlayRingtone`
- **THEN** 音频播放调用点为 todo 占位（无真实铃声副作用），铃声状态机按成功路径推进

### Requirement: 回铃音与等待音
系统 SHALL 由 `PlayRingback/StopRingback`、`PlayWaitingTone/StopWaitingTone`、`PlayCallEndedTone` 走 `PlayCallTone/StopCallTone`（音频 API 调用点以 `// todo!!! [audio]` 占位；`toneState_` 状态记录保留，原 `toneStateLock_` 递归互斥锁不迁移——单线程直接执行）；`PlayRingback` 受 `SetLocalRingbackNeeded` 设置的 `isLocalRingbackNeeded_` 控制（true→false 时自动 `StopRingback`）；DTMF 走 `PlayDtmfTone(char)`（`Tone::ConvertDigitToTone` 后播放 `DTMF_PLAY_TIME = 30` 毫秒，播放调用点占位）。
#### Scenario: 本地回铃音开关
- **WHEN** 协议栈侧设置 `SetLocalRingbackNeeded(false)` 且本地回铃音状态为播放中
- **THEN** 本地 `StopRingback` 状态切换立即执行

### Requirement: 音频设备路由
系统 SHALL 由 `AudioControlManager::GetInitAudioDeviceType()` 按收敛后的设备优先级固化：`IsEarpieceAvailable` 的 `DEVICE_EARPIECE` > `DEVICE_SPEAKER`（分布式汽车/星闪/蓝牙 SCO/有线耳机/助听器与前台视频/卫星/蓝牙通话强制扬声器分支不迁移）；`AudioDeviceManager::SwitchDevice(AudioDeviceType)` 仅分派 `EnableEarpiece/EnableSpeaker/DisableAll`（`EnableWiredHeadset/EnableBtSco/EnableNearlink/EnableBtHearingAid` 不迁移），`AudioProxy` 激活调用点以 `// todo!!! [audio]` 占位，随后 `SetCurrentAudioDevice` + `ReportAudioDeviceChange`（设备变化经回调上报）。
#### Scenario: 有线耳机拔出重路由
- **WHEN** 原有线耳机移除场景的等价输入到达（外设设备事件）
- **THEN** 有线耳机回补听筒链路已移除，路由维持听筒/扬声器收敛路径（`RemoveAudioDeviceList`/`AddEarpiece` 的耳机分支不迁移）

#### Scenario: 蓝牙通话暂时排除 SCO
- **WHEN** 原蓝牙通话场景的等价输入到达（如 `DEVICE_BLUETOOTH_SCO` 设备切换请求）
- **THEN** `ExcludeBluetoothSco`/`isScoTemporarilyDisabled_` 链路已移除，无 SCO 排除行为，按收敛后的设备分派处理

#### Scenario: 设备路由仅在听筒/扬声器间选择
- **WHEN** `InitAudioDevice` 评估设备类型
- **THEN** 仅在 `DEVICE_EARPIECE`（听筒可用时）与 `DEVICE_SPEAKER` 间选择，外设分支不可达

#### Scenario: 设备切换上报
- **WHEN** `SwitchDevice` 执行听筒/扬声器切换
- **THEN** 激活调用点为 todo 占位，当前设备状态更新并经 `ReportAudioDeviceChange` 回调上报

### Requirement: 麦克风静音
系统 SHALL 由 `AudioControlManager::SetMute(bool)` 在紧急呼叫时强制不静音（ECC 豁免保留）；`TYPE_BLUETOOTH` 活动通话走 `hfp_extra` 专用通道的分支不迁移；`AudioProxy::SetMicrophoneMute` 调用点以 `// todo!!! [audio]` 占位；随后 `ReportAudioDeviceInfo` 与 `SetMicPhoneState`（静音状态记录与上报保留）。
#### Scenario: 蓝牙通话静音走专用通道
- **WHEN** 活动通话中开启静音（`TYPE_BLUETOOTH` 场景已移除）
- **THEN** `hfp_extra` 专用通道分支不可达，静音状态经 `AudioProxy` 占位调用点记录并以 `ReportAudioDeviceInfo` 上报

#### Scenario: 紧急呼叫强制不静音
- **WHEN** 紧急呼叫通话中请求开启静音
- **THEN** 静音请求被强制拒绝（不静音），静音状态保持关闭

## REMOVED Requirements

### Requirement: 语音↔视频切换联动
**Reason**: AGENTS.md 功能范围：视频通话与视频彩振（crsType==CRS_TYPE）不支持。
**Migration**: `VideoStateUpdated`/`CheckTypeAndSetAudioDevice` 联动与 CRS 接听后 `UNMUTE_SOUNDTONE_DELAY_TIME = 500000` 微秒恢复音量逻辑不迁移；`RestoreVoiceValumeIfNecessary`/`GetBackupVoiceVolume` 调用点移除。

### Requirement: 视频彩振振动
**Reason**: AGENTS.md 功能范围：视频彩振不支持；`SUPPORT_VIBRATOR` 为不支持宏。
**Migration**: `NeedPlayVideoRing` 判定与 `StartVibrator`/`StopVibrator` 振动链路不迁移；`SystemSoundManager::GetCurrentRingtoneAttribute` 查询调用点移除。

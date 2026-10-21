# Audio Device Management Specification

## Purpose
描述 HMOS `telephony_call_manager` 中音频控制与设备路由能力的移植前现状：通话状态变化驱动的音频事件处理、音频场景状态机、设备选择与路由（听筒/扬声器/蓝牙/有线耳机）、铃声（含彩振 crsType、视频彩铃）、Sound/Tone 播放、麦克风静音与音量管理，以及对 audio_framework（AudioSystemManager/AudioGroupManager/AudioRoutingManager/AudioRenderer/TonePlayer/SystemSoundManager）的全部调用面。源码落点：`telephony_call_manager/services/audio/`（`audio_control_manager.cpp`、`audio_device_manager.cpp`、`audio_proxy.cpp`、`audio_scene_processor.cpp`、`call_state_processor.cpp`、`ring.cpp`、`sound.cpp`、`tone.cpp`、`audio_player.cpp` 及 `audio_state/` 下各状态 cpp）。控制本能力的构建开关：`SUPPORT_VIBRATOR`（`callmanager.gni` 在 `global_parts_info.sensors_miscdevice` 部件存在时定义，`#ifdef` 场点为 `audio_proxy.cpp` 的 vibrator include 与 `StartVibrator`）；`ABILITY_AUDIO_SUPPORT`（`#ifdef` 场点仅 `tone.cpp` 的 `Tone::GetToneDescriptorPath`，仓内 `callmanager.gni`/`BUILD.gn` 未定义该宏，默认构建走 `AudioProxy::GetDefaultTonePath` 分支）。本规格只描述现状，不涉及任何裁剪决策。

## Requirements

### Requirement: 音频子系统初始化与注销
系统 SHALL 由 `AudioControlManager::Init`（`audio_control_manager.cpp`）初始化 `AudioDeviceManager` 与 `AudioSceneProcessor` 两个 DelayedSingleton，并由 `AudioControlManager::UnInit` 通过 `AudioProxy::UnsetDeviceChangeCallback`、`UnsetAudioPreferDeviceChangeCallback`、`UnsetAudioMicStateChangeCallback` 注销全部 audio_framework 回调。`AudioDeviceManager::Init` SHALL 建立事件分发表（`ENABLE_DEVICE_EARPIECE/SPEAKER/WIRED_HEADSET/BLUETOOTH` → `EnableEarpiece/EnableSpeaker/EnableWiredHeadset/EnableBtSco`），将当前设备置为 `InactiveDeviceState`，并把 speaker 与 earpiece 放入初始 `info_.audioDeviceList`。

#### Scenario: 启动时耳机的可用性裁剪
- **WHEN** `AudioDeviceManager::UpdateEarpieceDevice` 被调用且 `IsSupportEarpiece`（查询 `AudioRoutingManager::GetAvailableDevices(CALL_OUTPUT_DEVICES)`）返回 false
- **THEN** 从 `info_.audioDeviceList` 移除 earpiece 且置 `isUpdateEarpieceDevice_` 防止重复裁剪

#### Scenario: 注销时清空回调
- **WHEN** `AudioControlManager::UnInit` 执行
- **THEN** 三类回调的 Unset 均被调用，audio_framework 侧不再向本模块投递设备/偏好设备/麦克风状态变化事件

### Requirement: 通话状态驱动音频事件
系统 SHALL 在 `AudioControlManager::CallStateUpdated` 中维护 `totalCalls_` 通话集合，经 `HandleCallStateUpdated`/`HandleNextState`/`HandlePriorState` 将 TelCallState 变化映射为 `AudioEvent`（NEW_DIALING/NEW_ALERTING/NEW_INCOMING/NEW_ACTIVE_CS/NEW_ACTIVE_IMS/NO_MORE_*），同步更新 `audioInterruptState_`（RINGING/ACTIVATED/DEACTIVATED），并把事件交给 `AudioSceneProcessor::ProcessEvent`。VOIP 类型通话 SHALL 走 `HandleCallStateUpdatedForVoip` 特例（仅 `GetPreferredOutputAudioDevice` 初始化听筒路由），不进入状态机。事件处理完 SHALL 调用 `UpdateForegroundLiveCall` 同步前台直播通话的麦克风静音状态（frontCall 与 `AudioProxy::IsMicrophoneMute` 不一致时调 `SetMute`）。

#### Scenario: 新通话纳入跟踪
- **WHEN** 一通非 VOIP 通话的 `CallStateUpdated` 首次进入
- **THEN** 通话对象插入 `totalCalls_`，状态变化映射为对应 AudioEvent 并提交 `AudioSceneProcessor`；断开态时从集合移除

#### Scenario: 接听前的静音铃声路径
- **WHEN** `nextState == CALL_STATUS_ANSWERED` 且 `priorState == CALL_STATUS_INCOMING`
- **THEN** 从 `CallStateProcessor` 删除该 incoming 记录、置 `SetIsAnsweredByPhone(true)` 并调用 `MuteRinger`（用户已接听，静音铃声而不是释放 renderer）；随后 ACTIVE 态经 `UnmuteSoundTone`（ffrt 延迟 500ms 的 `SetVoiceRingtoneMute(false)`）恢复彩振铃声

#### Scenario: 断开时停振动
- **WHEN** 通话进入 DISCONNECTING/DISCONNECTED 且不存在 crsType/视频彩铃来电
- **THEN** 若 `isCrsVibrating_` 或 `isVideoRingVibrating_` 为 true，调用 `AudioProxy::StopVibrator` 并复位两个标志

### Requirement: 音频场景状态机
系统 SHALL 由 `AudioSceneProcessor`（`audio_scene_processor.cpp`）以 ffrt 队列 `report_audio_state_change`（qos `ffrt_qos_user_interactive`）串行处理音频事件：`ProcessEvent` 立即返回 true 并提交 `ProcessEventInner`。`ProcessEventInner` SHALL 在切换状态前判断 `CallStateProcessor::ShouldStopSoundtone` 以停止彩振 Sound 并释放 disconnected 锁（`CallControlManager::ReleaseDisconnectedLock`），再按事件分发 `SwitchDialing/SwitchAlerting/SwitchIncoming/SwitchCS/SwitchIMS/SwitchHolding/SwitchInactive`。各状态 SHALL 由 `audio_state/` 下 `AudioBase` 派生类承接后续事件：`DialingState/AlertingState/IncomingState/CSCallState/IMSCallState/HoldingState/InActiveState/OTTCallState`（OTT 空实现直接返回 false）。

#### Scenario: 拨号态进入
- **WHEN** `SwitchDialing` 执行
- **THEN** 状态置为 `DialingState`；蓝牙类型通话且 SCO 未被临时排除时调用 `ExcludeBluetoothSco`；调用 `PlaySoundtone`、`UpdateDeviceTypeForVideoDialing` 并向 `AudioDeviceManager` 投递 `AUDIO_ACTIVATED`

#### Scenario: 来电态进入
- **WHEN** `SwitchIncoming` 执行且不存在 VOIP offhook/彩振等待音场景
- **THEN** 在语音播报、免打扰静音、非佩戴手表均不生效时 `StopRingtone` 后 `PlayRingtone`；`const.product.devicetype` 为 wearable 且上述任一条件成立时改走 `StopRingtone + PlayForNoRing`；随后投递 `AUDIO_RINGING`

#### Scenario: 回到空闲态
- **WHEN** `SwitchInactive` 执行
- **THEN** 先向 `AudioDeviceManager` 投递 `AUDIO_DEACTIVATED`，状态置为 `InActiveState`，若 SCO 曾被临时排除则调用 `UnexcludeBluetoothSco` 恢复

### Requirement: 通话状态簿记
系统 SHALL 由 `CallStateProcessor`（`call_state_processor.cpp`）用五个 `std::set<int32_t>`（dialing/alerting/incoming/active/holding）记录在途通话：`AddCall`/`DeleteCall` 按 TelCallState 归类；`ShouldSwitchState` 判定"仅剩该态且其他态为空"是否允许状态机切换；`UpdateCurrentCallState` 按 active > holding > incoming > dialing > alerting > inactive 的顺序重算并投递 `SWITCH_*` 事件；`ShouldStopSoundtone` 判定彩振 Sound 是否应停止（有 active 通话或带 crsType 的来电时不停止）；`GetAudioForegroundLiveCall`/`GetCurrentActiveCall` 返回相应优先级的 callId。

#### Scenario: 唯一来电才切状态
- **WHEN** `ShouldSwitchState(CALL_STATUS_INCOMING)` 被查询
- **THEN** 仅在 incoming 恰有 1 个且 active/dialing/alerting 均为空时返回 true

#### Scenario: 全部挂断后回落
- **WHEN** 最后一通通话离开其状态且 `UpdateCurrentCallState` 被调用
- **THEN** 投递 `SWITCH_AUDIO_INACTIVE_STATE` 使音频场景回到 `InActiveState`

### Requirement: 设备选择与 CurrentAudioDevice 切换
系统 SHALL 由 `AudioControlManager::SetAudioDevice`（两个重载，UI 切换携带 `isByUser`）在存在通话（`CallControlManager::HasCall/HasVoipCall`）的前提下分发设备类型：speaker/earpiece/wired headset 直接进入 `SwitchAudioDevice`；分布式设备走 `HandleDistributeAudioDevice`；蓝牙 SCO/Nearlink/HearingAid 先走 `HandleWirelessAudioDevice`。`AudioDeviceManager::SwitchDevice(AudioDeviceType)` SHALL 分派到 `EnableSpeaker/EnableEarpiece/EnableWiredHeadset/EnableBtSco/EnableNearlink/EnableBtHearingAid/DisableAll`，各 Enable 成功后经 `SetCurrentAudioDevice` 更新 `audioDeviceType_` 并 `ReportAudioDeviceChange`。初始设备类型 SHALL 由 `AudioControlManager::GetInitAudioDeviceType` 按优先级推导：语音态 bt sco > wired headset > hearing aid > earpiece > speaker；视频/卫星/蓝牙通话态强制 speaker（见其注释 `In voice call state, bluetooth sco > wired headset > earpiece > speaker`）；中断未激活时返回 `DEVICE_DISABLE`。

#### Scenario: UI 切换到扬声器
- **WHEN** `SetAudioDevice(DEVICE_SPEAKER)` 且当前存在通话
- **THEN** `EnableSpeaker` 在 `isSpeakerAvailable_` 为 true 且 `AudioProxy::SetSpeakerDevActive(true)` 成功后把 CurrentAudioDevice 置为 speaker 并上报设备变化

#### Scenario: 无通话时拒绝切换
- **WHEN** 不存在任何蜂窝/VOIP 通话时调用 `SetAudioDevice`
- **THEN** 返回 `CALL_ERR_AUDIO_SET_AUDIO_DEVICE_FAILED`，不触碰路由

#### Scenario: 音频激活时设备重建
- **WHEN** `AudioDeviceManager::ProcessEvent` 收到 `AUDIO_DEACTIVATED` 或 `INIT_AUDIO_DEVICE` 或外部设备断开
- **THEN** `InitAudioDevice` 用 `GetInitAudioDeviceType` 的结果重新 `SwitchDevice`，完成设备回退/重建

### Requirement: 蓝牙及无线设备路由
系统 SHALL 将蓝牙 SCO、Nearlink、HearingAid 三类无线设备的路由行为集中处理：`AudioDeviceManager::EnableBtSco` 依据 `IsBtActived`（`AudioRoutingManager::GetActiveBluetoothDevice` 非空即激活）；`EnableNearlink/EnableBtHearingAid` 依据 `AudioProxy::GetPreferredOutputAudioDevice` 返回的设备类型与地址。`AudioControlManager::HandleWirelessAudioDevice` SHALL 构造 `AudioDeviceDescriptor`（macAddress/deviceType/OUTPUT_DEVICE/LOCAL_NETWORK_ID）并以 `StreamUsage::STREAM_USAGE_VOICE_MODEM_COMMUNICATION` 的 `AudioRendererFilter` 调 `AudioSystemManager::SelectOutputDevice`；`GetWirelessAudioDeviceAddress` 分别经 `GetActiveBluetoothDevice`、`IsNearlinkActived`、`IsBtHearingAidActived` 取地址。SCO 临时排除 SHALL 由 `ExcludeBluetoothSco/UnexcludeBluetoothSco`（`ExcludeOutputDevices/UnexcludeOutputDevices(CALL_OUTPUT_DEVICES, ...)`）实现并维护 `isScoTemporarilyDisabled_`。`ReportAudioDeviceChange` 对无线设备 SHALL 经 `UpdateBtDevice/UpdateNearlinkDevice/UpdateBtHearingAidDevice` 回填地址与设备名，`ResetBtAudioDevicesList/ResetNearlinkAudioDevicesList/ResetBtHearingAidDeviceList` 在对应 SA 摘除时清列表并触发 `INIT_AUDIO_DEVICE`；`audio_state/BluetoothDeviceState` 承接 `BLUETOOTH_SCO_CONNECTED/DISCONNECTED` 事件。

#### Scenario: 切到蓝牙 SCO
- **WHEN** 活动蓝牙设备存在且 `SetAudioDevice(DEVICE_BLUETOOTH_SCO)` 被调用
- **THEN** `HandleWirelessAudioDevice` 以活动 SCO 地址 SelectOutputDevice 成功后 `EnableBtSco` 将 CurrentAudioDevice 置为蓝牙 SCO

#### Scenario: 蓝牙设备列表更新
- **WHEN** 蓝牙侧上报新 SCO 设备（`AddAudioDeviceList` 带 macAddress 与 deviceName）或 `UpdateBluetoothDeviceName` 被调用
- **THEN** `info_.audioDeviceList` 增改对应条目并 `ReportAudioDeviceInfo`；移除后无同类设备时 `SetDeviceAvailable(DEVICE_BLUETOOTH_SCO, false)`

#### Scenario: 分布式通话期间的 SCO 排除
- **WHEN** 拨号/来电为 `TYPE_BLUETOOTH` 且 `IsScoTemporarilyDisabled()` 为 false
- **THEN** `SwitchDialing/SwitchIncoming` 调用 `ExcludeBluetoothSco`；通话结束后 `SwitchInactive` 调用 `UnexcludeBluetoothSco` 恢复

### Requirement: 有线耳机路由
系统 SHALL 由 `AudioProxy::AudioDeviceChangeCallback::OnDeviceChange`（`audio_proxy.cpp`）监听 audio_framework 的 `DEVICE_TYPE_WIRED_HEADSET/WIRED_HEADPHONES/USB_HEADSET` 连接/断开：连接时 `SetWiredHeadsetState(true)` 并 `AudioDeviceManager::AddAudioDeviceList("", DEVICE_WIRED_HEADSET, "")`；断开时 `RemoveAudioDeviceList` 后投递 `WIRED_HEADSET_DISCONNECTED`。`AddAudioDeviceList` SHALL 在添加 wired headset 时从列表移除 earpiece（互斥），`RemoveAudioDeviceList` SHALL 在列表不再含 wired headset 且原本有 earpiece 时经 `AddEarpiece` 补回（仅当 `IsSupportEarpiece`）。`AudioProxy::SetWiredHeadsetDevActive` SHALL 要求 `isWiredHeadsetConnected_` 为 true 且用 `DEVICE_TYPE_USB_HEADSET` 激活；`SetEarpieceDevActive` SHALL 在有线耳机已连接时拒绝（返回 false）。`AudioDeviceManager::ProcessEvent` 收到 `WIRED_HEADSET_DISCONNECTED` SHALL 在通话激活期调 `CheckAndSwitchDistributedAudioDevice`。

#### Scenario: 插入有线耳机
- **WHEN** OnDeviceChange 报 CONNECT 且设备类型为有线耳机类
- **THEN** 耳机入设备列表（earpiece 被移除）、`SetDeviceAvailable(DEVICE_WIRED_HEADSET, true)`、设备信息上报

#### Scenario: 拔出有线耳机
- **WHEN** OnDeviceChange 报 DISCONNECT
- **THEN** 耳机出列表、可用性置 false、earpiece 按需补回，且通话中有视频/卫星通话时触发 `UpdateDeviceTypeForVideoOrSatelliteCall`

#### Scenario: 有线耳机未连接时激活被拒
- **WHEN** `isWiredHeadsetConnected_` 为 false 时调用 `SetWiredHeadsetDevActive`
- **THEN** 返回 false，路由不变

### Requirement: 视频通话/卫星通话的设备类型调整
系统 SHALL 由 `AudioControlManager::VideoStateUpdated`/`CheckTypeAndSetAudioDevice`（`audio_control_manager.cpp`）在视频状态切换时调整路由：音频转视频且非来电态时优先切到外部设备（有线/蓝牙/分布式），默认 speaker；视频转音频且非用户手动设定（`isSetAudioDeviceByUser_`）时回落到 earpiece（有外部设备则保留外部设备）；`originalCallType == VOICE_TYPE` 的 Dialing/Alerting/Disconnected 场景不设设备。`UpdateDeviceTypeForVideoOrSatelliteCall` SHALL 在前台通话为视频/卫星态时把路由切到外部设备或 speaker；`UpdateDeviceTypeForVideoDialing` SHALL 在拨号通话为 `TYPE_VIDEO` 时按初始设备类型切 speaker。卫星通话 SHALL 拒绝 earpiece：`SetAudioDevice` 遇 `HasSatelliteCallExist` 且 earpiece 时经 `CallDialog::DialogConnectExtension("SATELLITE_CALL_NOT_SUPPORT_EARPIECE")` 提示并失败；`AudioDeviceManager::SetCurrentAudioDevice` 对卫星通话强制 speaker。

#### Scenario: 音频转视频
- **WHEN** 视频状态从 `TYPE_VOICE` 变为 `TYPE_VIDEO` 且通话非 incoming/waiting
- **THEN** 路由切到外部设备（否则 speaker）

#### Scenario: 视频转音频回落
- **WHEN** 前一状态为视频、新状态为音频且未处于分布式 sink、`isSetAudioDeviceByUser_` 为 false
- **THEN** 路由回落到 earpiece（存在外部设备则用外部设备）

### Requirement: 来电铃声播放（含视频彩铃）
系统 SHALL 由 `AudioControlManager::PlayRingtone`（`audio_control_manager.cpp`）在 `ShouldPlayRingtone`（无 alerting 通话、有 incoming、ring 未在响、彩振 Sound 未占用）成立时创建 `Ring` 对象并播放：crsType 分支走彩振条；`CallObjectManager::IsVideoRing` 成立时按响铃模式启动振动（`isVideoRingVibrating_`）即短视频彩铃路径；否则 `Ring::Play`（`ring.cpp`）以 `Media::SystemSoundManagerFactory::CreateSystemSoundManager` + `GetSpecificRingTonePlayer(context, RINGTONE_TYPE_SIM_CARD_0/1, ringtonePath)` + `RingtonePlayer_->Configure(defaultVolume_, true)` + `Start(mode)`（蓝牙通话用 `HapticStartupMode::FAST`）播放系统铃声。`Ring::Stop/SetMute/SetRingToneVolume/ReleaseRenderer` SHALL 分别调用 RingtonePlayer 的对应接口并联动 `AudioPlayer::SetStop(TYPE_RING, ...)` 更新 `RingState`。`PostProcessRingtone` SHALL 检查来电 extraParams 的 `isNeedMuteRing` 以在播放成功后立刻静音。`PlayForNoRing/StopForNoRing` SHALL 用 `AudioRenderer::Create(STREAM_VOICE_RING)` 占用铃声流以抑制系统提示。`NeedPlayVideoRing/IsSystemVideoRing` SHALL 依赖 `AccountSA::OsAccountManager` 前台账户校验与 `SystemSoundManager::GetCurrentRingtoneAttribute` 的媒体类型判定。

#### Scenario: 普通来电振铃
- **WHEN** `SwitchIncoming` 触发 `PlayRingtone` 且来电无 crsType、无视频彩铃
- **THEN** RingtonePlayer 以 SIM 卡对应类型播放 `ringtonePath`，`RingState` 置 RINGING

#### Scenario: 短视频彩铃来电
- **WHEN** 来电命中 `IsVideoRing` 且响铃模式为 NORMAL+振动跟随设置 或 RINGER_MODE_VIBRATE
- **THEN** 不创建 RingtonePlayer，调用 `AudioProxy::StartVibrator` 启动视频彩铃振动（`isVideoRingVibrating_` 置位）

#### Scenario: 播放成功但需要静音
- **WHEN** 来电 WantParams 中 `isNeedMuteRing` 为 1
- **THEN** `PostProcessRingtone` 调用 `MuteRinger` 并把参数复位为 0

### Requirement: 彩振（crsType == CRS_TYPE）行为集中
系统 SHALL 将 crsType 为 `CRS_TYPE`（2）的来电彩振行为集中处理：`AudioControlManager::PlayRingtone` 命中 crsType 时走 `dealCrsScene`（响铃模式非 SILENT 时按振动模式启动 `isCrsVibrating_`；NORMAL 模式或有线/蓝牙接入时置 `isCrsStartSoundTone_` 并 `PlaySoundtone`（`Sound`+`AudioPlayer::Play(TYPE_SOUND)` 的虚拟采集通路）且 `AdjustVolumesForCrs`）。`MuteRinger` SHALL 对 crsType 来电调 `MuteNetWorkRingTone(true)`（`AudioProxy::SetVoiceRingtoneMute`）并在振动中时停振动；`ProcessSoundtone` SHALL 在 MT 通话被接听且无其他 active 通话时停/播彩振 Sound 并对 ringing 通话 `SetVoiceRingtoneMute(true)`，已被接听过则 `ResumeCrsSoundTone`（恢复音量并按 `initCrsDeviceType_` 切回原设备）。`AdjustVolumesForCrs` SHALL 把 STREAM_VOICE_CALL 音量调成 STREAM_RING 当前值并 `SaveVoiceVolume`；`RestoreVoiceValumeIfNecessary` SHALL 以 `SetVolumeWithDevice(STREAM_VOICE_CALL, ..., DEVICE_TYPE_SPEAKER)` 恢复并复位为 -1。`VideoStateUpdated`/`UpdateDeviceTypeForCrs` SHALL 在彩振来电进入时按响铃模式决定 speaker/初始耳内设备并记录 `initCrsDeviceType_`。彩振 Sound 的停止与锁定 SHALL 由 `AudioSceneProcessor::ProcessEventInner` 的 `ShouldStopSoundtone` 判断联动 `CallControlManager::ReleaseDisconnectedLock`。

#### Scenario: NORMAL 模式彩振来电
- **WHEN** crsType == CRS_TYPE 的来电振铃且响铃模式为 NORMAL
- **THEN** 启动彩振 Sound（虚拟 renderer/capturer 通路）、铃声音量套用到通话流、设备切 speaker

#### Scenario: 非普通模式彩振来电
- **WHEN** 响铃模式非 NORMAL
- **THEN** 若初始设备为耳内类（wired/bt sco/nearlink/hearing aid）则保持该设备不切 speaker；SILENT 模式不振动

#### Scenario: 彩振来电被接听
- **WHEN** 彩振通话被用户接听（`GetAnsweredByPhone`）且无其他 active 通话
- **THEN** `ResumeCrsSoundTone` 恢复原设备与原通话音量；`UnmuteSoundTone` 延迟 500ms 解除铃声流静音

### Requirement: 回铃音/等待音/结束音/DTMF 音
系统 SHALL 由 `AudioControlManager` 的 tone 族接口驱动 `Tone`（`tone.cpp`）：`PlayRingback` 要求 `isLocalRingbackNeeded_`（由 `SetLocalRingbackNeeded` 维护，false 时顺带 `StopRingback`）并播 `TONE_RINGBACK`；`PlayWaitingTone/StopWaitingTone` 对应 `TONE_WAITING`；`PlayCallEndedTone`（`CallEndedType` → `TONE_ENGAGED/TONE_FINISHED/TONE_UNKNOWN/TONE_INVALID_NUMBER`）在 VOIP 通话占用时不播、响铃模式非 NORMAL 时走 `HandleNotNormalRingerMode` 仅停音；`PlayDtmfTone` 用 `Tone::ConvertDigitToTone` 转换后播放 30ms。`Tone::Play` SHALL 对 DTMF/回铃/等待/结束音用 `AudioStandard::TonePlayer::Create(rendererInfo)` + `LoadTone(ConvertToneDescriptorToToneType)` + `StartTone`（非 TONE_FINISHED 时起 `TONE_PLAY_THREAD` 线程播放），`GetStreamUsageByToneType` 决定 streamUsage（DTMF → STREAM_USAGE_DTMF；RINGBACK → VOICE_MODEM_COMMUNICATION；WAITING 在 VOIP 占线时改 VOICE_COMMUNICATION；FINISHED → VOICE_RINGTONE）；其余描述符走 `AudioPlayer::Play(GetToneDescriptorPath(...), STREAM_MUSIC, TYPE_TONE)` 文件播放，其中 `Tone::GetToneDescriptorPath` 在 `#ifdef ABILITY_AUDIO_SUPPORT` 下调 `AudioProxy::GetToneDescriptorPath`（仓内无该宏定义，默认走 `GetDefaultTonePath`）。`toneState_` SHALL 由 `SetToneState`/`PlayCallTone`/`StopCallTone`（`ToneState::TONEING/STOPPED/CALLENDED`，`CALLENDED` 期间停音返回 `CALL_ERR_AUDIO_TONE_STOP_FAILED`）维护。

#### Scenario: 对端振铃播放本地回铃音
- **WHEN** 网络侧 `UpdateRBTPlayInfo(LOCAL_ALERTING)` 使 `SetLocalRingbackNeeded(true)` 后进入 ALERTING 态
- **THEN** `PlayRingback` 播放 TONE_RINGBACK；`isLocalRingbackNeeded_` 为 false 时返回失败不播

#### Scenario: 正常结束通话播放结束音
- **WHEN** 最后一通通话正常结束且响铃模式 NORMAL、无 VOIP 占用、`IsBtCallDisconnected` 为 false
- **THEN** 播 `TONE_FINISHED`，`toneState_` 经 CALLENDED、主线程 sleep 300ms 后停音回 TONEING

#### Scenario: 后拨字符逐个播 DTMF
- **WHEN** `CallStatusCallback::ReportPostDialChar` 触发 `OnPostDialNextChar(str)`
- **THEN** `PlayDtmfTone` 转换为 DTMF 描述符后用 TonePlayer 播 30ms 停止

### Requirement: 麦克风静音控制
系统 SHALL 由 `AudioControlManager::SetMute` 在存在通话且 `frontCall_` 非空时执行：紧急通话存在时强制 `isMute = false`；蓝牙通话为 active 时走 `AudioSystemManager::SetExtraParameters("hfp_extra", {"hfp_set_mic_mute"})` 并 `SetMicPhoneState`；否则 `AudioProxy::SetMicrophoneMute`（`AudioGroupManager::SetMicrophoneMute`）。操作后 SHALL `ReportAudioDeviceInfo`，并把实际麦克风状态（`IsMicrophoneMute`）写回非蓝牙通话的 `SetMicPhoneState`。`MuteRinger` SHALL 处理来电静音：停视频彩铃振动、crsType 时 `MuteNetWorkRingTone(true)`、发送 `EVENT_MUTE_RING`（`SendMuteRingEvent` → `CallAbilityReportProxy::CallEventUpdated`）、ring 已停时把来电 WantParams 置 `isNeedMuteRing=1`、否则 `Ring::SetMute`（`RingtonePlayer_->Configure(0, true)`）。

#### Scenario: 紧急通话强制不静音
- **WHEN** `CallControlManager::HasEmergency` 返回 true 时调用 `SetMute(true)`
- **THEN** 实际传给麦克风层的是 false

#### Scenario: 静音来电铃声
- **WHEN** 用户接听前调用 `MuteRinger` 且 RingtonePlayer 在播
- **THEN** RingtonePlayer Configure 音量 0，`isMutedRing_` 置位（后续 `SetRingToneVolume` 不生效）；app 侧收到 EVENT_MUTE_RING 事件

### Requirement: 音量管理
系统 SHALL 由 `AudioProxy` 转发 audio_framework 音量接口：`GetVolume/SetVolume/SetVolumeWithDevice/SetMaxVolume/GetMaxVolume/GetMinVolume/IsStreamActive/IsStreamMute`（`AudioSystemManager`）；`SetVolumeAudible` SHALL 把 STREAM_VOICE_CALL 设为最大值的一半（`VOLUME_AUDIBLE_DIVISOR`）；`GetSystemRingVolumeInDb` SHALL 经 `AudioGroupManager::GetSystemVolumeInDb(STREAM_RING, level, DEVICE_TYPE_SPEAKER)` 换算分贝。彩振专用音量保存/恢复（`SaveVoiceVolume/GetBackupVoiceVolume/RestoreVoiceValumeIfNecessary`、`AdjustVolumesForCrs`）归属彩振条。

#### Scenario: 结束通话恢复通话音量
- **WHEN** 彩振结束后 `RestoreVoiceValumeIfNecessary` 且 `voiceVolume_ >= 0`
- **THEN** 以 speaker 设备把 STREAM_VOICE_CALL 恢复为保存值并复位为 -1

#### Scenario: 可闻音量设置
- **WHEN** `SetVolumeAudible` 被调用
- **THEN** STREAM_VOICE_CALL 音量被设为最大值除以 VOLUME_AUDIBLE_DIVISOR

### Requirement: 设备信息上报
系统 SHALL 由 `AudioDeviceManager::ReportAudioDeviceChange`/`ReportAudioDeviceInfo`（`audio_device_manager.cpp`）组装 `AudioDeviceInfo` 并经 `CallAbilityReportProxy::ReportAudioDeviceChange` 上报：`ReportAudioDeviceChange` 在 `audioDeviceType_` 未知时先用 `GetInitAudioDeviceType` 兜底；蓝牙通话 active/dialing/alerting 时 SHALL 按 `BluetoothCallConnection::GetBtCallScoConnected` 把上报的 CurrentAudioDevice 映射为 speaker（SCO 已连）或 earpiece；`isMuted` 取自 VOIP/蓝牙通话对象或 `AudioProxy::IsMicrophoneMute`；`ConvertAddress` SHALL 对蓝牙/Nearlink/HearingAid 地址做脱敏（前 5 后 2 拼接 `:*:*:*:`），其余设备地址清空。

#### Scenario: 切换设备后上报
- **WHEN** `SetCurrentAudioDevice` 更新设备类型
- **THEN** `ReportAudioDeviceChange` 回填地址/设备名后 `ReportAudioDeviceInfo` 把设备信息与静音状态上报 app 侧

#### Scenario: 蓝牙通话的显示映射
- **WHEN** 存在 active 的 `TYPE_BLUETOOTH` 通话
- **THEN** 上报的当前设备按 SCO 连接状态映射为 speaker 或 earpiece，但模块内部 `audioDeviceType_` 不变

### Requirement: AudioPlayer 基础播放
系统 SHALL 由 `AudioPlayer`（`audio_player.cpp`）提供两类底层通路：wav 文件播放（`Play(path, streamType, playerType)`：解析 wav 头、`AudioRenderer::Create(streamType)` + `SetParams` + `SetRendererCallback(CallAudioRendererCallback)` + Start，循环 fread/Write，EOF 回卷）；虚拟采集通路（`Play(playerType)`：`InitRenderer` 以 96000/U8/MONO/`STREAM_USAGE_VOICE_MODEM_COMMUNICATION` 建 renderer，`InitCapturer` 以 `SOURCE_TYPE_VIRTUAL_CAPTURE` 建 capturer）。`SetStop` SHALL 按 PlayerType 同步 `AudioControlManager::SetRingState/SetToneState/SetSoundState`；`ReleaseRenderer/ReleaseCapturer` SHALL Flush/Drain/Stop/Release。`CallAudioRendererCallback::OnInterrupt` 与 `RingCallback::OnInterrupt` SHALL 在 `INTERRUPT_FORCE + INTERRUPT_HINT_STOP` 且铃声与彩振 Sound 同在时 `StopRingtone`；`RegisterRingCallback` 把 `RingCallback` 挂到 `Media::RingtonePlayer`。`Sound`（`sound.cpp`）SHALL 仅是 `AudioPlayer::Play(TYPE_SOUND)`/`SetStop`/`ReleaseRenderer/ReleaseCapturer` 的薄封装。

#### Scenario: 文件音播放与停止
- **WHEN** `AudioPlayer::Play` 以有效 wav 路径启动
- **THEN** renderer 按 wav 头参数流式播放直到 `IsStop(playerType)` 为 true 或循环被置停

#### Scenario: 强制打断
- **WHEN** audio_framework 投递 FORCE/STOP 打断事件且铃声与彩振 Sound 同时在播
- **THEN** `StopRingtone` 被调用结束播放

### Requirement: 振动器支持（SUPPORT_VIBRATOR）
系统 SHALL 仅在 `SUPPORT_VIBRATOR` 宏生效（`callmanager.gni` 依 `global_parts_info.sensors_miscdevice` 定义，`#ifdef` 场点在 `audio_proxy.cpp`）时接入 `Sensors::` 振动接口：`AudioProxy::StartVibrator` 以 `VIBRATION_RINGTONE` 类型按 `VIBRATOR_USAGE_MAP`（USAGE_RING）、`EFFECT_ID_MAP`（"haptic.ringtone.Dream_It_Possible"）`SetUsage` + `StartVibrator`，成功后起 ffrt 任务每 2 秒重触发直到 `loopFlag_` 复位；`StopVibrator` SHALL 仅置 `loopFlag_ = false`（下一次循环自然退出并 `Sensors::Cancel`）。宏未定义时 `StartVibrator` 直接返回成功值且不触碰 Sensors 接口。

#### Scenario: 彩振来电振动
- **WHEN** `dealCrsScene` 在振动模式或 NORMAL+振动跟随时调用 `StartVibrator`
- **THEN** 以铃声 effectId 循环振动，`isCrsVibrating_` 置位

#### Scenario: 停止振动
- **WHEN** 通话断开或 `MuteRinger` 调用 `StopVibrator`
- **THEN** `loopFlag_` 置 false，循环任务在下个 2 秒周期退出

### Requirement: AudioProxy 对 audio_framework 的调用面
系统 SHALL 将对 audio_framework 的全部调用集中在 `AudioProxy`（`audio_proxy.cpp`）与其回调类：设备激活（`SetDeviceActive`，VOIP 通话带 `voipCall->GetVoipUid()` 的三参重载、`SetBluetoothDevActive/SetSpeakerDevActive/SetWiredHeadsetDevActive/SetEarpieceDevActive`、`IsDeviceActive` 判断防重复）、路由查询（`GetPreferredOutputAudioDevice`：`AudioRoutingManager::GetPreferredOutputDeviceForRendererInfo`，`isNeedCurrentDevice` 决定 `STREAM_USAGE_INVALID` 与否，把 nearlink/sco/hearing aid/earpiece/speaker/wired 映射回 `AudioDeviceType`）、回调注册（`SetAudioDeviceChangeCallback`/`SetAudioPreferDeviceChangeCallback`/`SetAudioMicStateChangeCallback` 及各自 Unset）、麦克风与响铃模式（`AudioGroupManager::IsMicrophoneMute/SetMicrophoneMute/GetRingerMode`）、铃声流静音（`SetVoiceRingtoneMute`）、`SetVirtualCall`（`AudioSystemManager::SetVirtualCall`）。回调类 SHALL 完成事件回灌：`AudioDeviceChangeCallback::OnDeviceChange`（有线耳机插拔）、`AudioPreferDeviceChangeCallback::OnPreferredOutputDeviceUpdated`（有通话时按首选设备 `SetCurrentAudioDevice`，含 VOIP 特例 `ProcessVoipCallOutputDeviceUpdated`、分布式设备过滤 `IsDistributedDeviceSelected`、非 speaker 时联动 `UpdateDeviceTypeForCrs`）、`AudioMicStateChangeCallback::OnMicStateUpdated`（同步 `CallControlManager::SetMuted`）。

#### Scenario: 首选设备变化联动
- **WHEN** audio_framework 回调 `OnPreferredOutputDeviceUpdated` 且当前存在通话
- **THEN** 按新首选设备类型更新 CurrentAudioDevice；wired 类还需先 `AddAudioDeviceList`；非 speaker 设备触发 `UpdateDeviceTypeForCrs`

#### Scenario: 麦克风状态外部变化
- **WHEN** `OnMicStateUpdated` 收到麦克风静音变化
- **THEN** 以 `AudioGroupManager::IsMicrophoneMute()` 的实际值调用 `CallControlManager::SetMuted` 同步内部状态

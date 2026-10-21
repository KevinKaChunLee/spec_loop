# 音频管理（Audio Management）Specification

## Purpose
描述 HMOS `telephony_call_manager` 模块当前的通话音频管理能力：通话状态音频场景状态机（`AudioSceneProcessor` 与 `audio_state/` 下的 dialing/alerting/incoming/cs_call/ims_call/holding/inactive 状态类）、通话状态判定（`CallStateProcessor`）、设备路由状态机（`AudioDeviceManager` 与 earpiece/speaker/wired_headset/bluetooth/inactive 设备状态类）、振铃与提示音播放（`Ring`/`Sound`/`Tone`/`AudioPlayer`）、静音与音量控制（`AudioControlManager`），以及对 audio_framework / player_framework 系统 API 的封装层 `AudioProxy`。源码落点：`telephony_call_manager/services/audio/{include,src}`，主要文件为 audio_control_manager.cpp、audio_device_manager.cpp、audio_proxy.cpp、audio_scene_processor.cpp、call_state_processor.cpp、ring.cpp、sound.cpp、tone.cpp、audio_state/ 目录各状态类。控制开关：`callmanager.gni` 未为音频子模块定义专属编译开关；`SUPPORT_VIBRATOR`（随 sensors_miscdevice 部件打开）控制 `AudioProxy` 中振动相关逻辑，tone.cpp 中另有仅被引用未见 gni 定义的 `ABILITY_AUDIO_SUPPORT`。

## Requirements

### Requirement: 通话状态音频场景状态机
系统 SHALL 由 `AudioSceneProcessor`（延迟单例）持有当前通话音频场景状态 `currentState_`（初始为 `InActiveState`），通过 `Init` 注册 `memberFuncMap_` 将 `AudioEvent::SWITCH_DIALING_STATE`/`SWITCH_ALERTING_STATE`/`SWITCH_INCOMING_STATE`/`SWITCH_CS_CALL_STATE`/`SWITCH_IMS_CALL_STATE`/`SWITCH_HOLDING_STATE`/`SWITCH_AUDIO_INACTIVE_STATE` 映射到 SwitchDialing/SwitchAlerting/SwitchIncoming/SwitchCS/SwitchIMS/SwitchHolding/SwitchInactive 切态函数；`ProcessEvent` MUST 将事件经 ffrt 队列 `report_audio_state_change` 异步派发给 `ProcessEventInner` 串行处理；各场景状态类（DialingState、AlertingState、IncomingState、CSCallState、IMSCallState、HoldingState、InActiveState）按自身规则消费 NEW_*/NO_MORE_* 事件。

#### Scenario: CS 呼叫切换到 IMS
- **WHEN** 当前场景为 CSCallState，收到 `AudioEvent::CALL_TYPE_CS_CHANGE_IMS`
- **THEN** CSCallState::ProcessEvent 向 AudioSceneProcessor 转发 `AudioEvent::SWITCH_IMS_CALL_STATE`，场景切换到 IMS

#### Scenario: 活跃 CS 呼叫中来新来电
- **WHEN** 当前场景为 CSCallState，收到 `AudioEvent::NEW_INCOMING_CALL`
- **THEN** CSCallState::ProcessEvent 调用 AudioControlManager::PlayWaitingTone 播放等待音

#### Scenario: 非法切态事件
- **WHEN** `SwitchState(AudioEvent)` 在 `memberFuncMap_` 中找不到事件
- **THEN** 返回 false，场景状态不变

### Requirement: 通话状态判定
系统 SHALL 由 `CallStateProcessor`（延迟单例）用 activeCalls_/holdingCalls_/alertingCalls_/incomingCalls_/dialingCalls_ 五个 callId 集合跟踪各类通话；`AddCall`/`DeleteCall` 按 TelCallState 归类插入或删除；`ShouldSwitchState` MUST 在目标状态恰好存在 1 个通话（dialing/alerting/incoming 还要求其余三类集合为空）时返回 true；`UpdateCurrentCallState` 在 activeCalls_ 非空时不更新，否则按 holding > incoming > dialing > alerting > inactive 的优先级向 AudioSceneProcessor 派发对应 SWITCH_* 事件。

#### Scenario: 唯一拨号通话可切态
- **WHEN** dialingCalls_ 中恰有 1 个 callId 且 activeCalls_/incomingCalls_/alertingCalls_ 均为空，查询 ShouldSwitchState(CALL_STATUS_DIALING)
- **THEN** 返回 true

#### Scenario: 存在活跃通话时不更新场景
- **WHEN** activeCalls_ 非空时调用 UpdateCurrentCallState
- **THEN** 返回 false，不派发任何 SWITCH_* 事件

#### Scenario: 全部通话结束
- **WHEN** 五个集合全部为空时调用 UpdateCurrentCallState
- **THEN** 向 AudioSceneProcessor 派发 `AudioEvent::SWITCH_AUDIO_INACTIVE_STATE`

### Requirement: 设备路由状态机
系统 SHALL 由 `AudioDeviceManager`（延迟单例）维护当前通话输出设备 `audioDeviceType_` 与设备状态对象 `currentAudioDevice_`（初始 InactiveDeviceState）；`ProcessEvent(AUDIO_ACTIVATED/AUDIO_RINGING)` 在首次激活时经 `AudioProxy::GetPreferredOutputAudioDevice` 获取首选设备（默认 DEVICE_EARPIECE）并 `SetCurrentAudioDevice`；`SwitchDevice(AudioDeviceType)` 按 memberFuncMap_ 将 ENABLE_DEVICE_EARPIECE/SPEAKER/WIRED_HEADSET/BLUETOOTH 事件分派到 EnableEarpiece/EnableSpeaker/EnableWiredHeadset/EnableBtSco，各 Enable* MUST 先检查对应可用标志（isSpeakerAvailable_/isEarpieceAvailable_/isWiredHeadsetConnected_/IsBtActived）再经 AudioProxy 激活设备；设备状态类（SpeakerDeviceState、EarpieceDeviceState、WiredHeadsetDeviceState、BluetoothDeviceState、InactiveDeviceState）在外设连接事件到来时向 AudioDeviceManager 转发对应 ENABLE_DEVICE_* 事件。

#### Scenario: 首次激活选择首选设备
- **WHEN** isAudioActivated_ 为 false 时收到 `AudioEvent::AUDIO_ACTIVATED`
- **THEN** 置位 isAudioActivated_，取到首选设备后将当前设备置为该设备类型

#### Scenario: 扬声器状态下插入有线耳机
- **WHEN** 当前设备状态为 SpeakerDeviceState，收到 `AudioEvent::WIRED_HEADSET_CONNECTED`
- **THEN** SpeakerDeviceState::ProcessEvent 向 AudioDeviceManager 转发 `AudioEvent::ENABLE_DEVICE_WIRED_HEADSET`

#### Scenario: 蓝牙 SCO 不可用时切换失败
- **WHEN** IsBtActived() 返回 false 时 SwitchDevice(DEVICE_BLUETOOTH_SCO)
- **THEN** EnableBtSco 返回 false，当前设备不切换为蓝牙

### Requirement: 音频设备列表维护
系统 SHALL 由 `AudioDeviceManager::Init` 将 DEVICE_SPEAKER 与 DEVICE_EARPIECE 预置入 `info_.audioDeviceList`；`AddAudioDeviceList` 去重追加设备并在 DEVICE_WIRED_HEADSET 插入时移除 DEVICE_EARPIECE 条目，同时 `SetDeviceAvailable` 置位对应设备并 `ReportAudioDeviceInfo` 上报；`RemoveAudioDeviceList` 在同类型设备全部移除后 `SetDeviceAvailable` 置 false，有线耳机全部拔出且列表无耳机时回补 DEVICE_EARPIECE；`UpdateEarpieceDevice` MUST 经 `AudioStandard::AudioRoutingManager::GetAvailableDevices(CALL_OUTPUT_DEVICES)` 探测 DEVICE_TYPE_EARPIECE，不支持时从列表移除听筒。

#### Scenario: 插入有线耳机替换听筒
- **WHEN** AddAudioDeviceList(address, DEVICE_WIRED_HEADSET, name) 且列表中存在 DEVICE_EARPIECE 条目
- **THEN** DEVICE_EARPIECE 条目被移除，有线耳机入列表，SetDeviceAvailable(DEVICE_WIRED_HEADSET, true)，并上报设备信息

#### Scenario: 重复添加同地址同类型设备
- **WHEN** AddAudioDeviceList 传入的 address 与 deviceType 已存在于列表
- **THEN** 直接返回，列表不新增条目

#### Scenario: 设备不支持听筒
- **WHEN** UpdateEarpieceDevice 探测不到 DEVICE_TYPE_EARPIECE 输出设备
- **THEN** 从 info_.audioDeviceList 移除 DEVICE_EARPIECE 条目

### Requirement: 振铃播放
系统 SHALL 由 `AudioControlManager::PlayRingtone` 在 `ShouldPlayRingtone` 通过且存在 CALL_RUNNING_STATE_RINGING 通话时创建 `Ring` 对象播放振铃：`Ring::Init` 经 `Media::SystemSoundManagerFactory::CreateSystemSoundManager` 获取系统声音管理器，`Ring::Play` 按 slotId 选择 `Media::RingtoneType::RINGTONE_TYPE_SIM_CARD_0`（slotId 为 0）或 RINGTONE_TYPE_SIM_CARD_1，经 `GetSpecificRingTonePlayer` 取播放器，`Configure(defaultVolume_, true)` 后 `Start`；`Ring::Stop` 调用 RingtonePlayer 的 Stop 并复位 isMutedRing_；`Ring::SetMute` 将播放器音量 Configure 为 0。

#### Scenario: 播放默认振铃
- **WHEN** slotId=0 的来电满足播放条件，调用 Ring::Play(slotId=0, ringtonePath, mode)
- **THEN** 使用 RINGTONE_TYPE_SIM_CARD_0 的 RingtonePlayer 以默认音量开始播放

#### Scenario: 静音已停止的振铃
- **WHEN** ringState_ 已为 RingState::STOPPED 时调用 AudioControlManager::MuteRinger
- **THEN** 对振铃通话置 isNeedMuteRing 参数后返回 TELEPHONY_SUCCESS，不再触发 Stop

#### Scenario: 静音振铃置零音量
- **WHEN** RingtonePlayer 存在时调用 Ring::SetMute
- **THEN** isMutedRing_ 置 true，播放器被 Configure(0, true)

### Requirement: 提示音与 DTMF 播放
系统 SHALL 由 `Tone` 按 `ToneDescriptor` 播放提示音：DTMF 字符（0-9、*、#）经 `Tone::ConvertDigitToTone` 映射为 TONE_DTMF_CHAR_* 后用 `AudioStandard::TonePlayer`（STREAM_USAGE_DTMF）播放；TONE_RINGBACK/TONE_WAITING/TONE_FINISHED 同样走 TonePlayer（TONE_FINISHED 同步 Start，其余起线程异步播放）；`AudioControlManager::PlayRingback` MUST 在 `isLocalRingbackNeeded_` 为 false 时返回 CALL_ERR_AUDIO_TONE_PLAY_FAILED，为 true 时播放 TONE_RINGBACK；TONE_WAITING 的 streamUsage 在 VoIP 通话处于响铃/接听状态时改用 STREAM_USAGE_VOICE_COMMUNICATION。

#### Scenario: 无本地回铃需求时播放失败
- **WHEN** isLocalRingbackNeeded_ 为 false 时调用 AudioControlManager::PlayRingback
- **THEN** 返回 CALL_ERR_AUDIO_TONE_PLAY_FAILED，不产生任何播放

#### Scenario: 播放 DTMF 字符
- **WHEN** AudioControlManager::PlayDtmfTone('5')
- **THEN** 经 ConvertDigitToTone 得到 TONE_DTMF_CHAR_5，以 STREAM_USAGE_DTMF 的 TonePlayer 播放

#### Scenario: 停止非当前提示音
- **WHEN** tone_ 的当前类型不是 TONE_RINGBACK 时调用 AudioControlManager::StopRingback
- **THEN** 直接返回 TELEPHONY_SUCCESS，不调用 StopCallTone

### Requirement: Sound 播放
系统 SHALL 由 `Sound` 委托 `AudioPlayer::Play(TYPE_SOUND)` 播放彩振声音；`AudioControlManager::PlaySoundtone` 在 `IsDistributeCallSinkStatus()` 为真或 `soundState_` 已为 SOUNDING 时不播放（分别返回 true/false）；`StopSoundtone` 在 soundState_ 为 STOPPED 时直接返回 true。

#### Scenario: 已在播放时重复播放被拒绝
- **WHEN** soundState_ 为 SoundState::SOUNDING 时调用 AudioControlManager::PlaySoundtone
- **THEN** 返回 false，不创建新的 Sound 播放

#### Scenario: 停止已停止的 Sound
- **WHEN** soundState_ 为 SoundState::STOPPED 时调用 AudioControlManager::StopSoundtone
- **THEN** 返回 true，不再调用 sound_->Stop

### Requirement: 静音与音量控制
系统 SHALL 由 `AudioControlManager::SetMute` 控制麦克风静音：无任何通话时返回 CALL_ERR_AUDIO_SETTING_MUTE_FAILED；存在紧急呼叫时强制 isMute=false；存在 ACTIVE 的 TYPE_BLUETOOTH 通话时经 `AudioSystemManager::SetExtraParameters("hfp_extra", "hfp_set_mic_mute")` 下发，否则经 `AudioProxy::SetMicrophoneMute`（AudioGroupManager）设置，失败返回 CALL_ERR_AUDIO_SETTING_MUTE_FAILED；成功后按 `AudioProxy::IsMicrophoneMute` 实测值调用 `SetMicPhoneState` 并上报设备信息；`MuteRinger` MUST 先 StopVibrator（isVideoRingVibrating_ 时）再静音振铃。

#### Scenario: 无通话时静音失败
- **WHEN** CallControlManager::HasCall() 返回 false 时调用 SetMute(true)
- **THEN** 返回 CALL_ERR_AUDIO_SETTING_MUTE_FAILED

#### Scenario: 紧急呼叫强制解除静音
- **WHEN** HasEmergency(enabled) 返回成功且 enabled=true 时调用 SetMute(true)
- **THEN** 实际下发的是静音关闭（isMute 被改写为 false）

#### Scenario: 蓝牙通话静音走 HFP 参数
- **WHEN** 存在 CALL_STATUS_ACTIVE 的 TYPE_BLUETOOTH 通话时调用 SetMute(true)
- **THEN** 通过 AudioSystemManager::SetExtraParameters 以 "hfp_set_mic_mute"="true" 形式下发，并 SetMicPhoneState(true)

### Requirement: AudioProxy 系统音频封装
系统 SHALL 由 `AudioProxy`（延迟单例）集中封装 audio_framework 系统 API：设备激活（SetEarpieceDevActive/SetSpeakerDevActive/SetBluetoothDevActive/SetWiredHeadsetDevActive，经 AudioSystemManager::SetDeviceActive）、铃声模式与音量（GetRingerMode、GetVolume/SetVolume、SetVolumeAudible 将音量减半 VOLUME_AUDIBLE_DIVISOR）、铃声静音（SetVoiceRingtoneMute）、音频焦点（ActivateAudioInterrupt/DeactivateAudioInterrupt）、设备变化回调注册（SetAudioDeviceChangeCallback/UnsetDeviceChangeCallback，回调对象为 AudioDeviceChangeCallback/AudioPreferDeviceChangeCallback/AudioMicStateChangeCallback）；振动相关 StartVibrator/StopVibrator 仅在 `SUPPORT_VIBRATOR` 打开时生效；默认提示音路径为 "/system/etc/telephony/tones/tone.wav"、DTMF 为 "/system/etc/telephony/dtmfs/dtmf.wav"。

#### Scenario: 有线耳机未连接时激活失败
- **WHEN** isWiredHeadsetConnected_ 为 false 时调用 AudioProxy::SetWiredHeadsetDevActive
- **THEN** 返回 false，不调用 SetDeviceActive

#### Scenario: 获取默认提示音路径
- **WHEN** Tone 在 ABILITY_AUDIO_SUPPORT 未定义时调用 GetToneDescriptorPath
- **THEN** 返回 GetDefaultTonePath() 即 "/system/etc/telephony/tones/tone.wav"

#### Scenario: 通话音量设为最大值一半
- **WHEN** 调用 AudioProxy::SetVolumeAudible
- **THEN** STREAM_VOICE_CALL 音量被设置为 GetMaxVolume(STREAM_VOICE_CALL) 除以 VOLUME_AUDIBLE_DIVISOR(2) 的结果

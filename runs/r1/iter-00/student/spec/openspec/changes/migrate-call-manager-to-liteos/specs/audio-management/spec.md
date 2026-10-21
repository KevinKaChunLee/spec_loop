# Spec Delta

## MODIFIED Requirements

### Requirement: 通话状态音频场景状态机
系统 SHALL 由 `AudioSceneProcessor`（延迟单例）持有当前通话音频场景状态 `currentState_`（初始为 `InActiveState`），通过 `Init` 注册 `memberFuncMap_` 将 `AudioEvent::SWITCH_DIALING_STATE`/`SWITCH_ALERTING_STATE`/`SWITCH_INCOMING_STATE`/`SWITCH_CS_CALL_STATE`/`SWITCH_IMS_CALL_STATE`/`SWITCH_HOLDING_STATE`/`SWITCH_AUDIO_INACTIVE_STATE` 映射到 SwitchDialing/SwitchAlerting/SwitchIncoming/SwitchCS/SwitchIMS/SwitchHolding/SwitchInactive 切态函数；liteOS 上 OTT 类型通话不支持，`ott_call_state`（OttCallState）状态类及 OTT 相关事件映射 MUST NOT 迁移；`ProcessEvent` MUST 将事件经打桩 EventHandler 队列（替代 ffrt 队列 `report_audio_state_change`）异步派发给 `ProcessEventInner` 串行处理；各场景状态类（DialingState、AlertingState、IncomingState、CSCallState、IMSCallState、HoldingState、InActiveState）按自身规则消费 NEW_*/NO_MORE_* 事件；所有经 `AudioProxy` 的系统音频调用 MUST 在调用点写 `// todo!!! [audio] ref to audio_proxy.cpp <函数>`（以实际函数名为准）占位，待语音框架接口就绪后再适配。

#### Scenario: CS 呼叫切换到 IMS
- **WHEN** 当前场景为 CSCallState，收到 `AudioEvent::CALL_TYPE_CS_CHANGE_IMS`
- **THEN** CSCallState::ProcessEvent 向 AudioSceneProcessor 转发 `AudioEvent::SWITCH_IMS_CALL_STATE`，场景切换到 IMS（桩下可经 currentState_ 状态字段变化验证）

#### Scenario: 活跃 CS 呼叫中来新来电
- **WHEN** 当前场景为 CSCallState，收到 `AudioEvent::NEW_INCOMING_CALL`
- **THEN** CSCallState::ProcessEvent 调用 AudioControlManager::PlayWaitingTone，等待音播放的系统调用在调用点写 `// todo!!! [audio] ref to tone.cpp Play` 占位，判定逻辑不变

#### Scenario: 非法切态事件
- **WHEN** `SwitchState(AudioEvent)` 在 `memberFuncMap_` 中找不到事件
- **THEN** 返回 false，场景状态不变

### Requirement: 设备路由状态机
系统 SHALL 由 `AudioDeviceManager`（延迟单例）维护当前通话输出设备 `audioDeviceType_` 与设备状态对象 `currentAudioDevice_`（初始 InactiveDeviceState）；`ProcessEvent(AUDIO_ACTIVATED/AUDIO_RINGING)` 在首次激活时经 `AudioProxy::GetPreferredOutputAudioDevice` 获取首选设备（默认 DEVICE_EARPIECE，调用点写 `// todo!!! [audio] ref to audio_proxy.cpp GetPreferredOutputAudioDevice` 占位）并 `SetCurrentAudioDevice`；`SwitchDevice(AudioDeviceType)` 仅按 memberFuncMap_ 保留 `ENABLE_DEVICE_EARPIECE`/`ENABLE_DEVICE_SPEAKER` 事件分派到 EnableEarpiece/EnableSpeaker，各 Enable* MUST 先检查对应可用标志（isEarpieceAvailable_/isSpeakerAvailable_）再经 AudioProxy 激活设备（调用点写 `// todo!!! [audio] ref to audio_proxy.cpp SetEarpieceDevActive`/`SetSpeakerDevActive` 占位）；设备状态类仅保留 EarpieceDeviceState、SpeakerDeviceState、InactiveDeviceState，BluetoothDeviceState 与 WiredHeadsetDeviceState MUST NOT 迁移，WIRED_HEADSET/BLUETOOTH 外设连接事件转发与 ENABLE_DEVICE_WIRED_HEADSET/ENABLE_DEVICE_BLUETOOTH 分派及蓝牙 SCO 场景一并移除。

#### Scenario: 首次激活选择首选设备
- **WHEN** isAudioActivated_ 为 false 时收到 `AudioEvent::AUDIO_ACTIVATED`
- **THEN** 置位 isAudioActivated_，占位调用按默认值取首选设备后将当前设备置为该设备类型

#### Scenario: 扬声器不可用时切换失败
- **WHEN** isSpeakerAvailable_ 为 false 时 SwitchDevice(DEVICE_SPEAKER)
- **THEN** EnableSpeaker 返回 false，当前设备不切换为扬声器

#### Scenario: 扬声器状态下插入有线耳机
- **WHEN** 当前设备状态为 SpeakerDeviceState，桩注入 `AudioEvent::WIRED_HEADSET_CONNECTED`
- **THEN** WiredHeadsetDeviceState 与 `ENABLE_DEVICE_WIRED_HEADSET` 分派已随有线耳机不支持移除，事件不被转发处理，当前设备保持扬声器不变

#### Scenario: 蓝牙 SCO 不可用时切换失败
- **WHEN** 蓝牙链路已随 BLUETOOTH 类型通话不支持移除，SwitchDevice(DEVICE_BLUETOOTH_SCO) 无对应分派
- **THEN** 不存在 EnableBtSco 与 BluetoothDeviceState，切换返回 false，当前设备不切换为蓝牙

### Requirement: 音频设备列表维护
系统 SHALL 由 `AudioDeviceManager::Init` 将 DEVICE_SPEAKER 与 DEVICE_EARPIECE 预置入 `info_.audioDeviceList`，设备列表仅维护本机听筒/扬声器；`AddAudioDeviceList` 去重追加本机设备、`SetDeviceAvailable` 置位对应设备并 `ReportAudioDeviceInfo` 上报；有线耳机插入替换听筒、拔出回补及涉外部设备地址的重复添加语义 MUST 随有线耳机不支持一并移除；`UpdateEarpieceDevice` MUST 保留本机听筒判定逻辑，`AudioStandard::AudioRoutingManager::GetAvailableDevices(CALL_OUTPUT_DEVICES)` 探测调用点写 `// todo!!! [audio] ref to audio_device_manager.cpp UpdateEarpieceDevice` 占位，不支持时从列表移除 DEVICE_EARPIECE 条目。

#### Scenario: 初始化预置本机设备
- **WHEN** AudioDeviceManager::Init 执行完成
- **THEN** info_.audioDeviceList 中含 DEVICE_SPEAKER 与 DEVICE_EARPIECE 条目，不含任何外部设备条目

#### Scenario: 插入有线耳机替换听筒
- **WHEN** 桩注入有线耳机插入事件（基线 AddAudioDeviceList(address, DEVICE_WIRED_HEADSET, name) 路径）
- **THEN** 有线耳机替换听筒与拔出回补语义已随有线耳机不支持移除，info_.audioDeviceList 不含有线耳机条目、DEVICE_EARPIECE 条目不被移除，路由不切换

#### Scenario: 重复添加同地址同类型设备
- **WHEN** AddAudioDeviceList 传入的 address 与 deviceType 已存在于列表
- **THEN** 直接返回，列表不新增条目（去重逻辑保留，与基线一致）

#### Scenario: 设备不支持听筒
- **WHEN** UpdateEarpieceDevice 的占位探测按默认返回不支持 DEVICE_TYPE_EARPIECE 输出设备
- **THEN** 从 info_.audioDeviceList 移除 DEVICE_EARPIECE 条目

### Requirement: 振铃播放
系统 SHALL 由 `AudioControlManager::PlayRingtone` 在 `ShouldPlayRingtone` 通过且存在 CALL_RUNNING_STATE_RINGING 通话时创建 `Ring` 对象播放振铃：`Ring::Init`/`Ring::Play`/`Ring::Stop` 的系统铃声调用（SystemSoundManager/RingtonePlayer）MUST 在调用点写 `// todo!!! [audio] ref to ring.cpp Play`（及 Init/Stop，以实际函数名为准）占位，占位期间不真实发声；`Ring::Play` 按 slotId 选择 `Media::RingtoneType::RINGTONE_TYPE_SIM_CARD_0`（slotId 为 0）或 RINGTONE_TYPE_SIM_CARD_1 的分支逻辑保留；`Ring::Stop` 复位 isMutedRing_ 的去重状态逻辑保留；`Ring::SetMute` 将播放器音量置零的 Configure 调用点写 `// todo!!! [audio] ref to ring.cpp SetMute` 占位，isMutedRing_ 状态置位逻辑保留。

#### Scenario: 播放默认振铃
- **WHEN** slotId=0 的来电满足播放条件，调用 Ring::Play(slotId=0, ringtonePath, mode)
- **THEN** 走 RINGTONE_TYPE_SIM_CARD_0 分支，系统播放调用在调用点写 `// todo!!! [audio] ref to ring.cpp Play` 占位，桩下不真实发声但分支选择逻辑不变

#### Scenario: 静音已停止的振铃
- **WHEN** ringState_ 已为 RingState::STOPPED 时调用 AudioControlManager::MuteRinger
- **THEN** 对振铃通话置 isNeedMuteRing 参数后返回 TELEPHONY_SUCCESS，不再触发 Stop

#### Scenario: 静音振铃置零音量
- **WHEN** 振铃处于播放态时调用 Ring::SetMute
- **THEN** isMutedRing_ 置 true，音量置零的播放器调用在调用点写 `// todo!!! [audio] ref to ring.cpp SetMute` 占位

### Requirement: 提示音与 DTMF 播放
系统 SHALL 由 `Tone` 按 `ToneDescriptor` 播放提示音：DTMF 字符（0-9、*、#）经 `Tone::ConvertDigitToTone` 映射为 TONE_DTMF_CHAR_* 后用 `AudioStandard::TonePlayer`（STREAM_USAGE_DTMF）播放，映射逻辑保留；TONE_RINGBACK/TONE_WAITING/TONE_FINISHED 的播放调用 MUST 在调用点写 `// todo!!! [audio] ref to tone.cpp Play`（及 Stop，以实际函数名为准）占位，占位期间不真实发声；TONE_WAITING 的 VoIP streamUsage 分支 MUST 随 VoIP 通话不支持移除；`AudioControlManager::PlayRingback` MUST 在 `isLocalRingbackNeeded_` 为 false 时返回 CALL_ERR_AUDIO_TONE_PLAY_FAILED，为 true 时进入 TONE_RINGBACK 播放（调用点占位）；`StopRingback` 对非当前提示音直接返回 TELEPHONY_SUCCESS 的判定逻辑保留。

#### Scenario: 无本地回铃需求时播放失败
- **WHEN** isLocalRingbackNeeded_ 为 false 时调用 AudioControlManager::PlayRingback
- **THEN** 返回 CALL_ERR_AUDIO_TONE_PLAY_FAILED，不产生任何播放

#### Scenario: 播放 DTMF 字符
- **WHEN** AudioControlManager::PlayDtmfTone('5')
- **THEN** 经 ConvertDigitToTone 得到 TONE_DTMF_CHAR_5，系统 TonePlayer 播放调用在调用点写 `// todo!!! [audio] ref to tone.cpp Play` 占位，映射结果可测

#### Scenario: 停止非当前提示音
- **WHEN** tone_ 的当前类型不是 TONE_RINGBACK 时调用 AudioControlManager::StopRingback
- **THEN** 直接返回 TELEPHONY_SUCCESS，不调用 StopCallTone

### Requirement: Sound 播放
系统 SHALL 由 `Sound` 委托 `AudioPlayer::Play(TYPE_SOUND)` 播放彩振声音，系统播放调用 MUST 在调用点写 `// todo!!! [audio] ref to sound.cpp Play`（及 Stop，以实际函数名为准）占位，占位期间不真实发声；`AudioControlManager::PlaySoundtone` 的重复播放判定逻辑保留：`soundState_` 已为 SOUNDING 时不播放并返回 false（分布式 sink 场景随分布式通话不支持移除）；`StopSoundtone` 在 soundState_ 为 STOPPED 时直接返回 true。

#### Scenario: 已在播放时重复播放被拒绝
- **WHEN** soundState_ 为 SoundState::SOUNDING 时调用 AudioControlManager::PlaySoundtone
- **THEN** 返回 false，不创建新的 Sound 播放

#### Scenario: 停止已停止的 Sound
- **WHEN** soundState_ 为 SoundState::STOPPED 时调用 AudioControlManager::StopSoundtone
- **THEN** 返回 true，不再调用 sound_->Stop

### Requirement: 静音与音量控制
系统 SHALL 由 `AudioControlManager::SetMute` 控制麦克风静音：无任何通话时返回 CALL_ERR_AUDIO_SETTING_MUTE_FAILED；存在紧急呼叫时强制 isMute=false；TYPE_BLUETOOTH 通话的 HFP 参数下发分支 MUST 随蓝牙通话不支持移除，其余场景经 `AudioProxy::SetMicrophoneMute`（AudioGroupManager）设置，该系统调用点 MUST 写 `// todo!!! [audio] ref to audio_proxy.cpp SetMicrophoneMute` 占位，失败返回 CALL_ERR_AUDIO_SETTING_MUTE_FAILED；成功后按 `AudioProxy::IsMicrophoneMute` 占位返回的默认实测值调用 `SetMicPhoneState` 并上报设备信息；`MuteRinger` 的 StopVibrator 环节随 `SUPPORT_VIBRATOR` 不支持不迁移，静音振铃逻辑保留。

#### Scenario: 无通话时静音失败
- **WHEN** CallControlManager::HasCall() 返回 false 时调用 SetMute(true)
- **THEN** 返回 CALL_ERR_AUDIO_SETTING_MUTE_FAILED

#### Scenario: 紧急呼叫强制解除静音
- **WHEN** HasEmergency(enabled) 返回成功且 enabled=true 时调用 SetMute(true)
- **THEN** 实际下发的是静音关闭（isMute 被改写为 false）

#### Scenario: 蓝牙通话静音走 HFP 参数
- **WHEN** 存在 CALL_STATUS_ACTIVE 的 TYPE_BLUETOOTH 通话时调用 SetMute(true)
- **THEN** 蓝牙通话对象不存在（TYPE_BLUETOOTH 不迁移），该分支不触发，无 "hfp_set_mic_mute" SetExtraParameters 下发，静音统一走 `// todo!!! [audio] ref to audio_proxy.cpp SetMicrophoneMute` 占位路径

### Requirement: AudioProxy 系统音频封装
系统 SHALL 由 `AudioProxy`（延迟单例）保留集中封装 audio_framework 系统 API 的接口面：设备激活（SetEarpieceDevActive/SetSpeakerDevActive，经 AudioSystemManager::SetDeviceActive）、铃声模式与音量（GetRingerMode、GetVolume/SetVolume、SetVolumeAudible 将音量减半 VOLUME_AUDIBLE_DIVISOR）、铃声静音（SetVoiceRingtoneMute）、音频焦点（ActivateAudioInterrupt/DeactivateAudioInterrupt）、设备变化回调注册（SetAudioDeviceChangeCallback/UnsetDeviceChangeCallback，回调对象为 AudioDeviceChangeCallback/AudioPreferDeviceChangeCallback/AudioMicStateChangeCallback）；全部 AudioSystem/系统铃声相关 API 调用点 MUST 写 `// todo!!! [audio] ref to audio_proxy.cpp <函数>`（以实际函数名为准）占位，占位期间接口 SHALL 返回失败或默认值（bool 型返回 false、int32_t 型返回错误码或默认值），待语音框架接口就绪后再适配；StartVibrator/StopVibrator 随 `SUPPORT_VIBRATOR` 不支持不迁移；SetWiredHeadsetDevActive/SetBluetoothDevActive 随对应设备不支持移除；默认提示音路径保留 "/system/etc/telephony/tones/tone.wav"、DTMF 为 "/system/etc/telephony/dtmfs/dtmf.wav"。

#### Scenario: 获取默认提示音路径
- **WHEN** Tone 在 ABILITY_AUDIO_SUPPORT 未定义时调用 GetToneDescriptorPath
- **THEN** 返回 GetDefaultTonePath() 即 "/system/etc/telephony/tones/tone.wav"

#### Scenario: 有线耳机未连接时激活失败
- **WHEN** 桩注入有线耳机未连接状态（基线 isWiredHeadsetConnected_ 为 false 的场景）
- **THEN** `SetWiredHeadsetDevActive` 接口已随有线耳机不支持移除，不存在有线耳机激活链路，不产生任何 SetDeviceActive 调用，AudioProxy 设备激活仅保留听筒/扬声器

#### Scenario: 通话音量设为最大值一半
- **WHEN** 调用 AudioProxy::SetVolumeAudible
- **THEN** STREAM_VOICE_CALL 音量调用点写 `// todo!!! [audio] ref to audio_proxy.cpp SetVolumeAudible` 占位、不真实下发，GetMaxVolume(STREAM_VOICE_CALL) 除以 VOLUME_AUDIBLE_DIVISOR 的减半计算逻辑保留

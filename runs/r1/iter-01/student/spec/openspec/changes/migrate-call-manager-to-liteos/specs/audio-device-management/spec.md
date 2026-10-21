# Spec Delta

## REMOVED Requirements

### Requirement: 蓝牙及无线设备路由

**Reason**: AGENTS「功能范围」不支持 BLUETOOTH 类型通话与星闪（NearLink）耳机设备连接，`SUPPORT_HEARING_AID` 属不支持宏（「特性宏支持范围」）；design D7 `ABILITY_BLUETOOTH_SUPPORT` 宏处置行明确 audio 路由的蓝牙分支删除；`BluetoothCallConnection` 随 telephony-interaction 删除后本需求的 SCO 状态查询点消失。
**Migration**: 删除 `services/audio/` 下 `audio_device_manager.{h,cpp}`/`audio_control_manager.{h,cpp}`/`audio_proxy.{h,cpp}` 中的 `EnableBtSco`/`EnableNearlink`/`EnableBtHearingAid`/`HandleWirelessAudioDevice`/`GetWirelessAudioDeviceAddress`/`ExcludeBluetoothSco`/`UnexcludeBluetoothSco`/`isScoTemporarilyDisabled_`/`IsBtActived`/`UpdateBtDevice`/`UpdateNearlinkDevice`/`UpdateBtHearingAidDevice`/`UpdateBluetoothDeviceName`/`ResetBtAudioDevicesList`/`ResetNearlinkAudioDevicesList`/`ResetBtHearingAidDeviceList` 及 `AudioSystemManager::SelectOutputDevice`（`ExcludeOutputDevices`/`UnexcludeOutputDevices(CALL_OUTPUT_DEVICES, ...)`）的无线出口，并同步 `callmanager.gni`；删除设备状态类 `services/audio/src/audio_state/bluetooth_device_state.cpp/.h`（含 `services/audio/include/audio_state/` 下对应头文件）；`ReportAudioDeviceInfo` 的蓝牙显示映射与 `audioDeviceList` 无线条目维护点随删（见本 delta「设备信息上报」）。恢复条件：接入蓝牙 HFP/星闪/听力辅音频框架后按基线重建无线路由族与 SCO 排除链。

### Requirement: 有线耳机路由

**Reason**: AGENTS「功能范围」明确 liteOS 不支持有线耳机；design D7 被删文件表列出 `services/call/call_state_observer/src/wired_headset.cpp` 与 `services/call/src/call_wired_headset.cpp`。
**Migration**: `services/audio` 侧删除 `AudioProxy::AudioDeviceChangeCallback::OnDeviceChange` 的有线耳机插拔处理（`SetWiredHeadsetState`、`AddAudioDeviceList`/`RemoveAudioDeviceList` 的 wired headset 与 earpiece 互斥及 `IsSupportEarpiece` 补回链、`WIRED_HEADSET_DISCONNECTED` 事件）、`AudioProxy::SetWiredHeadsetDevActive`/`isWiredHeadsetConnected_`、设备状态类 `services/audio/src/audio_state/wired_headset_device_state.cpp/.h`；`AudioDeviceManager::ProcessEvent` 收到 `WIRED_HEADSET_DISCONNECTED` 时调 `CheckAndSwitchDistributedAudioDevice` 的分支连同分布式音频路由函数族（`CheckAndSwitchDistributedAudioDevice`/`IsDistributedCallConnected`/`IsDistributedAudioDeviceType`，`audio_device_manager.cpp`）一并删除（AGENTS 不支持分布式通话，design D7 `services/distributed_call/` 删除，`SUPPORT_DSOFTBUS` 零引用无迁移动作）；`AudioControlManager::SetAudioDevice` 对 `HandleDistributeAudioDevice` 的分发分支删除（见本 delta「设备选择与 CurrentAudioDevice 切换」）。恢复条件：接入有线耳机框架后重建插拔观察与互斥补回链；支持分布式通话后重建分布式音频路由族。

### Requirement: 视频通话/卫星通话的设备类型调整

**Reason**: AGENTS「功能范围」明确 liteOS 不支持视频通话与卫星通话；design D7 被删文件表列出 `video_call_state.cpp`、`satellite_call.cpp`、`satellite_call_control.cpp`。
**Migration**: 删除 `audio_control_manager.{h,cpp}` 的 `VideoStateUpdated`/`CheckTypeAndSetAudioDevice`/`UpdateDeviceTypeForVideoOrSatelliteCall`/`UpdateDeviceTypeForVideoDialing`/`NeedPlayVideoRing`/`IsSystemVideoRing`（依赖 `AccountSA::OsAccountManager` 前台账户校验与 `SystemSoundManager::GetCurrentRingtoneAttribute` 的短视频彩铃路径整体取消）、`SetAudioDevice` 对 `CallObjectManager::HasSatelliteCallExist()` + `DEVICE_EARPIECE` 的拒绝链（`CallDialog::DialogConnectExtension("SATELLITE_CALL_NOT_SUPPORT_EARPIECE")`）、`AudioDeviceManager::SetCurrentAudioDevice` 对卫星通话强制 speaker 的分支。恢复条件：支持视频/卫星通话后按基线重建设备类型调整链。

### Requirement: 彩振（crsType == CRS_TYPE）行为集中

**Reason**: AGENTS「功能范围」明确 liteOS 不支持视频彩振（crsType==CRS_TYPE），相关代码无需迁移。
**Migration**: 删除 `audio_control_manager.{h,cpp}` 的 `dealCrsScene`/`AdjustVolumesForCrs`/`ResumeCrsSoundTone`/`UpdateDeviceTypeForCrs` 与彩振标志、暂态字段（`isCrsVibrating_`/`isCrsStartSoundTone_`/`initCrsDeviceType_`）；`PlayRingtone` 的 crsType 分支、`MuteRinger` 的彩振 `MuteNetWorkRingTone(true)` 分支、`ProcessSoundtone`/`UnmuteSoundTone` 的彩振 Sound 停止/恢复链删除（`SetVoiceRingtoneMute` 出口本身在保留需求中经 `[audio]` 桩化）；彩振专用音量保存/恢复族 `SaveVoiceVolume`/`GetBackupVoiceVolume`/`RestoreVoiceValumeIfNecessary` 随彩振删除（对等改写见本 delta「音量管理」）；`CallStateProcessor::ShouldStopSoundtone` 删除"带 crsType 的来电时不停止"判定项（保留"有 active 通话时不停止"，见本 delta「通话状态簿记」）。恢复条件：引入彩振业务后按基线重建虚拟通路消费链与音量套用链。

### Requirement: 振动器支持（SUPPORT_VIBRATOR）

**Reason**: AGENTS「特性宏支持范围」将 `SUPPORT_VIBRATOR` 列入不支持宏；design D7 宏处置表：gni `sensors_miscdevice` 部件块与 `audio_proxy.cpp` 守卫块删除。
**Migration**: 删除 `services/audio/src/audio_proxy.cpp` 的两处 `#ifdef SUPPORT_VIBRATOR` 宏块与 Sensors include、`AudioProxy::StartVibrator`/`StopVibrator`、`VIBRATOR_USAGE_MAP`/`EFFECT_ID_MAP`、`loopFlag_` 振动循环任务（2 秒重触发语义一并消失）；`callmanager.gni` 的 `global_parts_info.sensors_miscdevice` 部件块删除（design D7 宏清理）；`isCrsVibrating_`/`isVideoRingVibrating_` 置位点随彩振与视频彩铃路径删除（见本 delta「通话状态驱动音频事件」「来电铃声播放」）。恢复条件：接入 miscdevice 振动框架后按 effectId 循环振动链重建。

## MODIFIED Requirements

### Requirement: 音频子系统初始化与注销

系统 SHALL 由 `AudioControlManager::Init`（`services/audio/src/audio_control_manager.cpp`）初始化 `AudioDeviceManager` 与 `AudioSceneProcessor` 两个 DelayedSingleton（模板形态保留，design D5），并由 `AudioControlManager::UnInit` 经 `AudioProxy::UnsetDeviceChangeCallback`、`UnsetAudioPreferDeviceChangeCallback`、`UnsetAudioMicStateChangeCallback` 注销全部 audio_framework 回调——liteOS 上三个 Unset 的 audio_framework 调用点标 `// todo!!! [audio] ref to audio_proxy.cpp UnsetDeviceChangeCallback` 等占位（design D6 audio 行），桩默认失败时仅走基线"注销失败记日志"分支。`AudioDeviceManager::Init` SHALL 仅保留 `ENABLE_DEVICE_EARPIECE/SPEAKER` → `EnableEarpiece/EnableSpeaker` 分发表项、当前设备置 `InactiveDeviceState`，并把 speaker 与 earpiece 放入初始 `info_.audioDeviceList`；基线 `ENABLE_DEVICE_WIRED_HEADSET/ENABLE_BLUETOOTH` 表项与设备状态类 `WiredHeadsetDeviceState`/`BluetoothDeviceState` 随有线/蓝牙删除（见本 delta REMOVED 条）。

#### Scenario: 启动时耳机的可用性裁剪
- **WHEN** `AudioDeviceManager::UpdateEarpieceDevice` 被调用且 `IsSupportEarpiece`（查询 `AudioRoutingManager::GetAvailableDevices(CALL_OUTPUT_DEVICES)`，调用点经 `[audio]` todo 桩）返回 false
- **THEN** 走基线 false 分支：从 `info_.audioDeviceList` 移除 earpiece 且置 `isUpdateEarpieceDevice_` 防止重复裁剪；桩配置成功且耳机可用时 earpiece 保留（判定逻辑照抄）

#### Scenario: 注销时清空回调
- **WHEN** `AudioControlManager::UnInit` 执行
- **THEN** 三类 Unset 调用点经 `[audio]` todo 桩执行；桩默认失败时仅记日志（基线失败分支照抄），liteOS 上 audio_framework 侧本无回调可投递

测试落点：`call_manager_zero_gtest`（音频面用例所在 `tel_call_manager_zero9_gtest`/`tel_call_manager_zero10_gtest` 套件）新增 `Telephony_AudioInit_01x` 系用例（桩失败/成功两态下 earpiece 裁剪与 Unset 链）。

### Requirement: 通话状态驱动音频事件

系统 SHALL 在 `AudioControlManager::CallStateUpdated` 中维护 `totalCalls_` 通话集合，经 `HandleCallStateUpdated`/`HandleNextState`/`HandlePriorState` 将 TelCallState 变化映射为 `AudioEvent`（NEW_DIALING/NEW_ALERTING/NEW_INCOMING/NEW_ACTIVE_CS/NEW_ACTIVE_IMS/NO_MORE_*），同步更新 `audioInterruptState_`（RINGING/ACTIVATED/DEACTIVATED），并把事件交给 `AudioSceneProcessor::ProcessEvent`（以上居中逻辑全部照抄）。VOIP 类型通话 SHALL 保留 `HandleCallStateUpdatedForVoip` 特例（仅经 `GetPreferredOutputAudioDevice` 初始化听筒路由，该出口经 `[audio]` todo 桩），不进入状态机。事件处理完 SHALL 照抄调用 `UpdateForegroundLiveCall` 同步前台直播通话的麦克风静音状态（frontCall 与 `AudioProxy::IsMicrophoneMute` 不一致时调 `SetMute`，出口经 `[audio]` todo 桩）。基线彩振相关联动（接听后 `UnmuteSoundTone` 延迟 500ms 的 `SetVoiceRingtoneMute(false)` 恢复段、断开时 `StopVibrator` 停振段）随彩振/振动删除（见本 delta REMOVED 条）。

#### Scenario: 新通话纳入跟踪
- **WHEN** 一通非 VOIP 通话的 `CallStateUpdated` 首次进入
- **THEN** 通话对象插入 `totalCalls_`，状态变化映射为对应 AudioEvent 并提交 `AudioSceneProcessor`；断开态时从集合移除（行为照抄基线）

#### Scenario: 接听前的静音铃声路径
- **WHEN** `nextState == CALL_STATUS_ANSWERED` 且 `priorState == CALL_STATUS_INCOMING`
- **THEN** 从 `CallStateProcessor` 删除该 incoming 记录、置 `SetIsAnsweredByPhone(true)` 并调用 `MuteRinger`（用户已接听，静音铃声而不是释放 renderer）照抄；基线"随后 ACTIVE 态经 `UnmuteSoundTone` 恢复彩振铃声"段因彩振不支持删除，liteOS 上无该恢复路径

#### Scenario: 断开时停振动
- **WHEN** 通话进入 DISCONNECTING/DISCONNECTED
- **THEN** 因振动器不支持（`SUPPORT_VIBRATOR` 宏块删除）且彩振/视频彩铃标志字段已随彩振删除，断开路径不存在 `isCrsVibrating_`/`isVideoRingVibrating_` 判定与 `AudioProxy::StopVibrator` 调用；其余断开处理照抄基线

测试落点：`tel_call_manager_zero9_gtest`/`tel_call_manager_zero10_gtest` 套件新增 `Telephony_AudioEvent_01x` 系用例（totalCalls_ 增删、AudioEvent 映射矩阵、VOIP 特例不入状态机、frontCall 静音同步经桩注入驱动）。

### Requirement: 音频场景状态机

系统 SHALL 由 `AudioSceneProcessor`（`services/audio/src/audio_scene_processor.cpp`）以串行任务队列处理音频事件：基线 ffrt 队列 `report_audio_state_change`（`reportAudioStateChangeQueue`）改打桩 EventHandler 的串行任务队列（`stub/eventhandler_stub`，design D8；桩内同步逐条执行、不新增线程，qos `ffrt_qos_user_interactive` 语义随 ffrt 消失不迁移）；`ProcessEvent` 立即返回 true 并提交 `ProcessEventInner`。`ProcessEventInner` SHALL 在切换状态前判断 `CallStateProcessor::ShouldStopSoundtone`（彩振判定项已删）并联动 `CallControlManager::ReleaseDisconnectedLock`（该功耗锁调用点经 `[powerLock]` todo 桩化，design D6 功耗锁行），再按事件分发 `SwitchDialing/SwitchAlerting/SwitchIncoming/SwitchCS/SwitchIMS/SwitchHolding/SwitchInactive`。各状态 SHALL 由 `audio_state/` 下 `AudioBase` 派生类承接后续事件：`DialingState/AlertingState/IncomingState/CSCallState/IMSCallState/HoldingState/InActiveState` 保留；`OTTCallState`（OTT 空实现直接返回 false）随 OTT 类型通话删除（`services/audio/src/audio_state/ott_call_state.cpp/.h` 删除并同步 `callmanager.gni`）。

#### Scenario: 拨号态进入
- **WHEN** `SwitchDialing` 执行
- **THEN** 状态置为 `DialingState` 并向 `AudioDeviceManager` 投递 `AUDIO_ACTIVATED`；基线中的蓝牙 SCO 排除（`ExcludeBluetoothSco`）、彩振 `PlaySoundtone` 调用与 `UpdateDeviceTypeForVideoDialing` 分支均已删除，liteOS 不存在这些路径

#### Scenario: 来电态进入
- **WHEN** `SwitchIncoming` 执行且不存在 VOIP offhook 场景
- **THEN** 在免打扰静音（`IsNeedSilentInDoNotDisturbMode`）与非佩戴手表（`IsNotWearOnWrist`，settings 键 `wear_status` 查询经 `[database]` todo 桩化）均不生效时 `StopRingtone` 后 `PlayRingtone`；`const.product.devicetype` 为 wearable 且上述任一条件成立时改走 `StopRingtone + PlayForNoRing`（参数读取经 `stub/parameter_stub`）；全部播放出口经 `[audio]` todo 桩、桩失败走基线失败分支；基线"语音播报判定"（HiCar 语音助手）分支随 `call_voice_assistant_manager.cpp` 删除（design D7）而移除，基线"彩振等待音场景"条件项随彩振删除；随后投递 `AUDIO_RINGING`

#### Scenario: 回到空闲态
- **WHEN** `SwitchInactive` 执行
- **THEN** 先向 `AudioDeviceManager` 投递 `AUDIO_DEACTIVATED`，状态置为 `InActiveState`；基线"若 SCO 曾被临时排除则调用 `UnexcludeBluetoothSco` 恢复"分支随蓝牙删除

测试落点：`tel_call_manager_zero9_gtest` 套件新增 `Telephony_AudioSceneProcessor_01x` 系用例（串行队列顺序断言、SWITCH_* 分发矩阵、删除分支不可达断言）。

### Requirement: 通话状态簿记

系统 SHALL 由 `CallStateProcessor`（`services/audio/src/call_state_processor.cpp`）用五个 `std::set<int32_t>`（dialing/alerting/incoming/active/holding）记录在途通话：`AddCall`/`DeleteCall` 按 TelCallState 归类；`ShouldSwitchState` 判定"仅剩该态且其他态为空"是否允许状态机切换；`UpdateCurrentCallState` 按 active > holding > incoming > dialing > alerting > inactive 的顺序重算并投递 `SWITCH_*` 事件——以上全部照抄。`ShouldStopSoundtone` SHALL 保留"有 active 通话时不停止"判定、删除基线"有带 crsType 的来电时不停止"判定项（彩振删除后 Sound 消费者不存在）。`GetAudioForegroundLiveCall`/`GetCurrentActiveCall` 照抄返回相应优先级的 callId。

#### Scenario: 唯一来电才切状态
- **WHEN** `ShouldSwitchState(CALL_STATUS_INCOMING)` 被查询
- **THEN** 仅在 incoming 恰有 1 个且 active/dialing/alerting 均为空时返回 true（行为照抄基线）

#### Scenario: 全部挂断后回落
- **WHEN** 最后一通通话离开其状态且 `UpdateCurrentCallState` 被调用
- **THEN** 投递 `SWITCH_AUDIO_INACTIVE_STATE` 使音频场景回到 `InActiveState`（行为照抄基线）

测试落点：`tel_call_manager_zero9_gtest` 套件新增 `Telephony_CallStateProcessor_01x` 系用例（五集合归类、ShouldSwitchState 边界、ShouldStopSoundtone 仅 active 判定）。

### Requirement: 设备选择与 CurrentAudioDevice 切换

系统 SHALL 由 `AudioControlManager::SetAudioDevice`（两个重载，UI 切换携带 `isByUser`）在存在通话（`CallControlManager::HasCall/HasVoipCall`）的前提下分发设备类型——liteOS 上设备路由收敛为听筒/扬声器：speaker/earpiece 直接进入 `SwitchAudioDevice`；基线"分布式设备走 `HandleDistributeAudioDevice`"分支删除（AGENTS 不支持分布式通话）；"蓝牙 SCO/Nearlink/HearingAid 先走 `HandleWirelessAudioDevice`"分支删除（AGENTS 不支持蓝牙/星闪/听力辅）。`AudioDeviceManager::SwitchDevice(AudioDeviceType)` SHALL 仅分派 `EnableSpeaker/EnableEarpiece/DisableAll`（含默认分支），基线 `EnableWiredHeadset/EnableBtSco/EnableNearlink/EnableBtHearingAid` 分派项删除；各 Enable 成功后经 `SetCurrentAudioDevice` 更新 `audioDeviceType_` 并 `ReportAudioDeviceChange` 照抄。初始设备类型 SHALL 由 `AudioControlManager::GetInitAudioDeviceType` 按收敛后的优先级推导：语音态仅 earpiece > speaker（基线注释 `In voice call state, bluetooth sco > wired headset > earpiece > speaker` 的前 2 项随蓝牙/有线删除、hearing aid 项随其删除）；基线"视频/卫星/蓝牙通话态强制 speaker"推导分支删除（这些通话形态在 liteOS 不存在）；中断未激活时返回 `DEVICE_DISABLE` 照抄。

#### Scenario: UI 切换到扬声器
- **WHEN** `SetAudioDevice(DEVICE_SPEAKER)` 且当前存在通话
- **THEN** `EnableSpeaker` 在 `isSpeakerAvailable_` 为 true 且 `AudioProxy::SetSpeakerDevActive(true)` 成功（桩配置成功）后把 CurrentAudioDevice 置为 speaker 并上报设备变化；桩默认失败时走基线激活失败分支，不更新 CurrentAudioDevice

#### Scenario: 无通话时拒绝切换
- **WHEN** 不存在任何蜂窝/VOIP 通话时调用 `SetAudioDevice`
- **THEN** 返回 `CALL_ERR_AUDIO_SET_AUDIO_DEVICE_FAILED`，不触碰路由（行为照抄基线）

#### Scenario: 音频激活时设备重建
- **WHEN** `AudioDeviceManager::ProcessEvent` 收到 `AUDIO_DEACTIVATED` 或 `INIT_AUDIO_DEVICE`
- **THEN** `InitAudioDevice` 用 `GetInitAudioDeviceType` 的结果重新 `SwitchDevice`，完成设备回退/重建照抄；基线"或外部设备断开"触发项随有线/蓝牙删除，liteOS 仅剩上述两类事件触发重建

测试落点：`tel_call_manager_zero10_gtest` 套件新增 `Telephony_AudioDevice_01x` 系用例（收敛后路由分派矩阵、优先级推导、桩失败/成功两态、无通话拒绝错误码）。

### Requirement: 来电铃声播放（含视频彩铃）

系统 SHALL 由 `AudioControlManager::PlayRingtone`（`audio_control_manager.cpp`）在 `ShouldPlayRingtone`（无 alerting 通话、有 incoming、ring 未在响——基线"彩振 Sound 未占用"项删除）成立时创建 `Ring` 对象并播放：基线 crsType 彩振条删除（见本 delta REMOVED 条）；基线 `CallObjectManager::IsVideoRing` 命中时按响铃模式启动振动（`isVideoRingVibrating_`）的短视频彩铃路径删除（振动器支持 REMOVED，`IsVideoRing` 判定在通话对象面保留，见 call-object-management delta）；否则 `Ring::Play`（`services/audio/src/ring.cpp`）以 `Media::SystemSoundManagerFactory::CreateSystemSoundManager` + `GetSpecificRingTonePlayer(context, RINGTONE_TYPE_SIM_CARD_0/1, ringtonePath)` + `RingtonePlayer_->Configure(defaultVolume_, true)` + `Start(mode)` 的全部 audio Framework 调用点标 `// todo!!! [audio] ref to ring.cpp Play`（design D6 audio 行），播放成功/失败返回语义照抄（桩默认失败时走基线 `RingtonePlayer_` 为空的失败分支，不置 RINGING）；基线"蓝牙通话用 `HapticStartupMode::FAST`"参数分支随蓝牙通话删除（普通路径 `HapticStartupMode::DEFAULT` 照抄）。`Ring::Stop/SetMute/SetRingToneVolume/ReleaseRenderer` SHALL 分别联动 `AudioPlayer::SetStop(TYPE_RING, ...)` 更新 `RingState`（RingtonePlayer 侧调用经 `[audio]` 桩）。`PostProcessRingtone` SHALL 保留检查来电 extraParams 的 `isNeedMuteRing` 以在播放成功后立刻静音。`PlayForNoRing/StopForNoRing` SHALL 保留用 `AudioRenderer::Create(STREAM_VOICE_RING)` 占用铃声流以抑制系统提示（出口 `[audio]` 桩）。基线 `NeedPlayVideoRing/IsSystemVideoRing` 删除（本 delta REMOVED「视频通话/卫星通话的设备类型调整」）。

#### Scenario: 普通来电振铃
- **WHEN** `SwitchIncoming` 触发 `PlayRingtone` 且来电无 crsType、无视频彩铃（两项判定已删，liteOS 恒普通路径）
- **THEN** Ring 播放经 `[audio]` 桩：桩配置成功时以 SIM 卡对应类型播放 `ringtonePath`、`RingState` 置 RINGING；桩默认失败时走基线播放失败分支（不置 RINGING）

#### Scenario: 短视频彩铃来电
- **WHEN** 来电命中 `IsVideoRing`（联系人 `personalNotificationRingtone`/`ringtonePath` 判定在对象面保留）
- **THEN** 因振动器不支持（`SUPPORT_VIBRATOR` 宏块删除）与视频彩铃振动路径删除，liteOS 上不再创建"不播 RingtonePlayer 而启动 `AudioProxy::StartVibrator`"的行为，`isVideoRingVibrating_` 置位路径不迁移；该类来电落入普通铃播放路径

#### Scenario: 播放成功但需要静音
- **WHEN** 来电 WantParams 中 `isNeedMuteRing` 为 1 且播放成功
- **THEN** `PostProcessRingtone` 调用 `MuteRinger` 并把参数复位为 0（行为照抄基线）

测试落点：`tel_call_manager_zero10_gtest` 套件新增 `Telephony_Ring_01x` 系用例（ShouldPlayRingtone 判定、桩两态下 RingState、isNeedMuteRing 复位、PlayForNoRing 铃声流占用记账）。

### Requirement: 回铃音/等待音/结束音/DTMF 音

系统 SHALL 由 `AudioControlManager` 的 tone 族接口驱动 `Tone`（`services/audio/src/tone.cpp`），居中逻辑照抄：`PlayRingback` 要求 `isLocalRingbackNeeded_`（由 `SetLocalRingbackNeeded` 维护，false 时顺带 `StopRingback`）并播 `TONE_RINGBACK`；`PlayWaitingTone/StopWaitingTone` 对应 `TONE_WAITING`（保留，基线视频升级触发链的删除见 telephony-interaction delta）；`PlayCallEndedTone`（`CallEndedType` → `TONE_ENGAGED/TONE_FINISHED/TONE_UNKNOWN/TONE_INVALID_NUMBER`）在 VOIP 通话占用时不播、响铃模式非 NORMAL 时走 `HandleNotNormalRingerMode` 仅停音（VOIP 判定照抄）；`PlayDtmfTone` 用 `Tone::ConvertDigitToTone` 转换后播放 30ms。`Tone::Play` SHALL 对 DTMF/回铃/等待/结束音经 `AudioStandard::TonePlayer::Create(rendererInfo)` + `LoadTone(ConvertToneDescriptorToToneType)` + `StartTone`（非 TONE_FINISHED 时起 `TONE_PLAY_THREAD` 线程播放——行为照抄）执行，`GetStreamUsageByToneType` 的映射照抄（DTMF → STREAM_USAGE_DTMF；RINGBACK → VOICE_MODEM_COMMUNICATION；WAITING 在 VOIP 占线时改 VOICE_COMMUNICATION；FINISHED → VOICE_RINGTONE）；其余描述符走 `AudioPlayer::Play(GetToneDescriptorPath(...), STREAM_MUSIC, TYPE_TONE)` 文件播放。liteOS 上全部 TonePlayer/audio_framework 调用点标 `[audio]` todo、成功/失败语义照抄；`Tone::GetToneDescriptorPath` 的 `#ifdef ABILITY_AUDIO_SUPPORT` 宏块仓内未定义恒走 `GetDefaultTonePath`，按实际代码仅活性分支照抄（design「宏定义按实际代码实现来判断」）。`toneState_` SHALL 由 `SetToneState`/`PlayCallTone`/`StopCallTone`（`ToneState::TONEING/STOPPED/CALLENDED`，`CALLENDED` 期间停音返回 `CALL_ERR_AUDIO_TONE_STOP_FAILED`）维护照抄。

#### Scenario: 对端振铃播放本地回铃音
- **WHEN** 网络侧 `UpdateRBTPlayInfo(LOCAL_ALERTING)` 使 `SetLocalRingbackNeeded(true)` 后进入 ALERTING 态
- **THEN** `PlayRingback` 播 `TONE_RINGBACK` 经 `[audio]` 桩；`isLocalRingbackNeeded_` 为 false 时返回失败不播（照抄）；上行触发链经 telephony-interaction 桩直调注入

#### Scenario: 正常结束通话播放结束音
- **WHEN** 最后一通通话正常结束且响铃模式 NORMAL、无 VOIP 占用
- **THEN** 基线"`IsBtCallDisconnected` 为 false"判定项随蓝牙删除（恒 false 路径），播 `TONE_FINISHED` 经 `[audio]` 桩，`toneState_` 经 CALLENDED、主线程 sleep 300ms 后停音回 TONEING（照抄）

#### Scenario: 后拨字符逐个播 DTMF
- **WHEN** `CallStatusCallback::ReportPostDialChar` 触发 `OnPostDialNextChar(str)`
- **THEN** `PlayDtmfTone` 转换为 DTMF 描述符后用 TonePlayer 播 30ms 停止（经 `[audio]` 桩，照抄）

测试落点：`tel_call_manager_zero9_gtest` 套件新增 `Telephony_Tone_01x` 系用例（toneState 状态机、四类映射、isLocalRingbackNeeded 门控、桩两态返回码）。

### Requirement: 麦克风静音控制

系统 SHALL 由 `AudioControlManager::SetMute` 在存在通话且 `frontCall_` 非空时执行：紧急通话存在时强制 `isMute = false`（`IsEmergencyCallExists` 判定链保留，见 `audio_control_manager.cpp`）；基线"蓝牙通话为 active 时走 `AudioSystemManager::SetExtraParameters("hfp_extra", {"hfp_set_mic_mute"})`"分支随蓝牙删除；否则 `AudioProxy::SetMicrophoneMute`（`AudioGroupManager::SetMicrophoneMute`）出口经 `[audio]` todo 桩、成功/失败语义照抄。操作后 SHALL `ReportAudioDeviceInfo`，并把实际麦克风状态（`IsMicrophoneMute` 经桩读取）写回非 VoIP 通话的 `SetMicPhoneState` 照抄（基线"非蓝牙通话"限定词随蓝牙删除）。`MuteRinger` SHALL 处理来电静音：基线"停视频彩铃振动"分支删除、crsType 时 `MuteNetWorkRingTone(true)` 分支删除（本 delta REMOVED 彩振条；`SetVoiceRingtoneMute` 出口保留经 `[audio]` 桩）、发送 `EVENT_MUTE_RING`（`SendMuteRingEvent` → `CallAbilityReportProxy::CallEventUpdated`，上报出口无 IPC 直调回调，design D2/D3）、ring 已停时把来电 WantParams 置 `isNeedMuteRing=1`、否则 `Ring::SetMute`（`RingtonePlayer_->Configure(0, true)` 经 `[audio]` 桩）——以上保留路径照抄。

#### Scenario: 紧急通话强制不静音
- **WHEN** `IsEmergencyCallExists`/`CallControlManager::HasEmergency` 返回 true 时调用 `SetMute(true)`
- **THEN** 实际传给麦克风层的是 false（照抄；桩出口断言收到的 mute 参数为 false）

#### Scenario: 静音来电铃声
- **WHEN** 用户接听前调用 `MuteRinger` 且 RingtonePlayer 在播（桩配置）
- **THEN** `Ring::SetMute` 经 `[audio]` 桩执行（桩侧记账 `RingtonePlayer_->Configure(0, true)` 等价调用），`isMutedRing_` 置位（后续 `SetRingToneVolume` 不生效）；app 侧经直调回调收到 EVENT_MUTE_RING 事件

测试落点：`tel_call_manager_zero10_gtest` 套件新增 `Telephony_AudioMute_01x` 系用例（紧急强制不静音、MuteRinger 四分支（停振/彩振两分支已删的负向断言）、EVENT_MUTE_RING 直调上报）。

### Requirement: 音量管理

系统 SHALL 由 `AudioProxy` 转发 audio_framework 音量接口，调用点逐一标 `[audio]` todo、返回语义照抄（桩默认失败走基线失败分支、测试可配桩返回值）：`GetVolume/SetVolume/SetVolumeWithDevice/SetMaxVolume/GetMaxVolume/GetMinVolume/IsStreamActive/IsStreamMute`（`AudioSystemManager`）；`SetVolumeAudible` SHALL 把 STREAM_VOICE_CALL 设为最大值的一半（`VOLUME_AUDIBLE_DIVISOR` 照抄）；`GetSystemRingVolumeInDb` SHALL 经 `AudioGroupManager::GetSystemVolumeInDb(STREAM_RING, level, DEVICE_TYPE_SPEAKER)` 换算分贝（经 `[audio]` 桩）。基线归属彩振条的音量保存/恢复族（`SaveVoiceVolume`/`GetBackupVoiceVolume`/`RestoreVoiceValumeIfNecessary`/`AdjustVolumesForCrs`）随彩振删除，`voiceVolume_` 的保存值恒为初始 -1、恢复路径不可达（本 delta REMOVED 彩振条）。

#### Scenario: 结束通话恢复通话音量
- **WHEN** 基线彩振结束后 `RestoreVoiceValumeIfNecessary` 且保存值 ≥ 0
- **THEN** 因彩振（crsType==CRS_TYPE）不支持，`SaveVoiceVolume` 写点已随彩振删除、保存值恒 -1，该恢复路径不迁移、场景不可达（见本 delta REMOVED 彩振条）

#### Scenario: 可闻音量设置
- **WHEN** `SetVolumeAudible` 被调用
- **THEN** STREAM_VOICE_CALL 音量被设为最大值除以 `VOLUME_AUDIBLE_DIVISOR`（计算照抄，SetVolume 经 `[audio]` 桩下发）

测试落点：`tel_call_manager_zero9_gtest` 套件新增 `Telephony_AudioVolume_01x` 系用例（SetVolumeAudible 换算、桩转发记账、彩振恢复路径不可达断言）。

### Requirement: 设备信息上报

系统 SHALL 由 `AudioDeviceManager::ReportAudioDeviceChange`/`ReportAudioDeviceInfo`（`services/audio/src/audio_device_manager.cpp`）组装 `AudioDeviceInfo` 并上报：上报出口 `CallAbilityReportProxy::ReportAudioDeviceChange` 按 design D2/D3 改直调回调对象（无 IPC）；`ReportAudioDeviceChange` 在 `audioDeviceType_` 未知时先用 `GetInitAudioDeviceType` 兜底照抄；基线"蓝牙通话 active/dialing/alerting 时按 `BluetoothCallConnection::GetBtCallScoConnected` 映射 speaker/earpiece"分支删除（BluetoothCallConnection 文件已删，蓝牙通话不存在）；`isMuted` SHALL 取自 VOIP 通话对象或 `AudioProxy::IsMicrophoneMute`（经 `[audio]` 桩，基线蓝牙通话对象取值项删除）；`ConvertAddress` SHALL 删除蓝牙/Nearlink/HearingAid 地址脱敏分支（前 5 后 2 拼接系列），仅保留其余设备地址清空照抄。

#### Scenario: 切换设备后上报
- **WHEN** `SetCurrentAudioDevice` 更新设备类型
- **THEN** `ReportAudioDeviceChange` 回填地址/设备名后 `ReportAudioDeviceInfo` 把设备信息与静音状态经直调回调上报 app 侧（行为照抄基线，仅出口直调化）

#### Scenario: 蓝牙通话的显示映射
- **WHEN** 基线存在 active 的 `TYPE_BLUETOOTH` 通话
- **THEN** 因 BLUETOOTH 类型通话不支持（AGENTS「功能范围」），liteOS 对象表中不存在该类型通话，SCO 连接状态映射分支删除，该场景不迁移（见本 delta REMOVED「蓝牙及无线设备路由」条）

测试落点：`tel_call_manager_zero10_gtest` 套件新增 `Telephony_AudioReport_01x` 系用例（未知设备兜底、isMuted 取值链、蓝牙映射负向断言、直调上报记账）。

### Requirement: AudioPlayer 基础播放

系统 SHALL 由 `AudioPlayer`（`services/audio/src/audio_player.cpp`）提供两类底层通路，全部 audio_framework 调用点标 `[audio]` todo、成功/失败语义照抄：wav 文件播放（`Play(path, streamType, playerType)`：解析 wav 头、`AudioRenderer::Create(streamType)` + SetParams + SetRendererCallback(CallAudioRendererCallback) + Start、循环 fread/Write、EOF 回卷）；虚拟采集通路（`Play(playerType)`：`InitRenderer` 以 96000/U8/MONO/`STREAM_USAGE_VOICE_MODEM_COMMUNICATION` 建 renderer，`InitCapturer` 以 `SOURCE_TYPE_VIRTUAL_CAPTURE` 建 capturer）。`SetStop` SHALL 按 PlayerType 同步 `AudioControlManager::SetRingState/SetToneState/SetSoundState` 照抄；`ReleaseRenderer/ReleaseCapturer` SHALL Flush/Drain/Stop/Release 照抄。`CallAudioRendererCallback::OnInterrupt` 与 `RingCallback::OnInterrupt` SHALL 在 `INTERRUPT_FORCE + INTERRUPT_HINT_STOP` 且铃声在播时 `StopRingtone`（基线"铃声与彩振 Sound 同在"条件中的彩振项删除——彩振 Sound 消费链已移除，`Sound`（`services/audio/src/sound.cpp`）薄封装照抄保留供桩独立验证）；`RegisterRingCallback` 把 `RingCallback` 挂到 `Media::RingtonePlayer`（经 `[audio]` 桩）照抄。

#### Scenario: 文件音播放与停止
- **WHEN** `AudioPlayer::Play` 以有效 wav 路径启动（桩配置成功）
- **THEN** renderer 按 wav 头参数流式播放直到 `IsStop(playerType)` 为 true 或循环被置停（照抄；桩失败时走基线创建失败分支）

#### Scenario: 强制打断
- **WHEN** 桩注入 `INTERRUPT_FORCE + INTERRUPT_HINT_STOP` 打断事件且铃声在播
- **THEN** `StopRingtone` 被调用结束播放（彩振 Sound 同在条件删除后仅判铃声照抄基线单铃声路径）

测试落点：`tel_call_manager_zero9_gtest` 套件新增 `Telephony_AudioPlayer_01x` 系用例（wav 解析参数、SetStop 状态联动、OnInterrupt 打断停铃）。

### Requirement: AudioProxy 对 audio_framework 的调用面

系统 SHALL 将对 audio_framework 的全部调用集中在 `AudioProxy`（`services/audio/src/audio_proxy.cpp`）与其回调类，liteOS 上按"暂不调用（todo 占位）"处置（design D6 audio 行），逐调用点标 `// todo!!! [audio] ref to audio_proxy.cpp <函数名>`，成功/失败返回语义照抄（桩默认失败走基线失败分支、测试可配置桩返回值与回调注入）。保留面：设备激活 `SetDeviceActive`（VOIP 通话带 `voipCall->GetVoipUid()` 的三参重载保留）、`SetSpeakerDevActive`/`SetEarpieceDevActive`、`IsDeviceActive` 防重复判断、路由查询 `GetPreferredOutputAudioDevice`（`AudioRoutingManager::GetPreferredOutputDeviceForRendererInfo`，`isNeedCurrentDevice` 决定 `STREAM_USAGE_INVALID` 与否——映射仅保留 earpiece/speaker/wired 中的 earpiece/speaker 两项，nearlink/sco/hearing aid/wired 映射项随其删除）、回调注册 `SetAudioDeviceChangeCallback`/`SetAudioPreferDeviceChangeCallback`/`SetAudioMicStateChangeCallback` 及各自 Unset、麦克风与响铃模式 `IsMicrophoneMute/SetMicrophoneMute/GetRingerMode`（`AudioGroupManager`）、铃声流静音 `SetVoiceRingtoneMute`、`SetVirtualCall`（`AudioSystemManager::SetVirtualCall`）。删除面：`SetBluetoothDevActive`/`SetWiredHeadsetDevActive`（蓝牙/有线 REMOVED）。回调类 SHALL 保留事件回灌语义：`AudioDeviceChangeCallback::OnDeviceChange` 的有线耳机插拔分支删除（回调注入面保留）；`AudioPreferDeviceChangeCallback::OnPreferredOutputDeviceUpdated` 在有通话时按首选设备 `SetCurrentAudioDevice` 保留——VOIP 特例 `ProcessVoipCallOutputDeviceUpdated` 保留、分布式设备过滤 `IsDistributedDeviceSelected` 删除、wired 类 `AddAudioDeviceList` 删除、非 speaker 联动 `UpdateDeviceTypeForCrs` 删除；`AudioMicStateChangeCallback::OnMicStateUpdated` 同步 `CallControlManager::SetMuted` 保留。

#### Scenario: 首选设备变化联动
- **WHEN** 桩注入 `OnPreferredOutputDeviceUpdated` 且当前存在通话
- **THEN** 按新首选设备类型更新 CurrentAudioDevice（仅 speaker/earpiece 生效）；基线"wired 类还需先 `AddAudioDeviceList`"、"非 speaker 设备触发 `UpdateDeviceTypeForCrs`"、分布式过滤分支均已删除

#### Scenario: 麦克风状态外部变化
- **WHEN** 桩注入 `OnMicStateUpdated` 收到麦克风静音变化
- **THEN** 以 `AudioGroupManager::IsMicrophoneMute()` 的实际值（`[audio]` 桩读数）调用 `CallControlManager::SetMuted` 同步内部状态（照抄）

测试落点：`tel_call_manager_zero9_gtest`/`tel_call_manager_zero10_gtest` 套件新增 `Telephony_AudioProxy_01x` 系用例（回调注入链三路、GetPreferredOutputAudioDevice 收敛映射、桩默认失败分支）。
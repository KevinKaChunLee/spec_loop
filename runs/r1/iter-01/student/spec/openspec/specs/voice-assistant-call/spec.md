# Voice Assistant Call Specification

## Purpose
描述 HMOS `telephony_call_manager` 中通话语音播报/助手管理（`services/call_voice_assistant/src/call_voice_assistant_manager.cpp`，头文件 `services/call_voice_assistant/include/call_voice_assistant_manager.h`）的移植前现状：`CallVoiceAssistantManager`（进程内单例 `GetInstance`）在来话/去电时按 datashare 开关（`CONTROL_SWITCH` 控制开关、`BROADCAST_SWITCH` 播报开关）拉起语音助手 ability 并经 IPC 同步来话信息，控制助手侧播报与系统铃音的让位关系；`VoiceAssistantRingSubscriber` 订阅助手侧广播决定是否接管系统铃音播放。异步动作统一经 `ffrt::queue callVoiceAssistantQueue` 提交。本模块无特性宏门控；经 `call_control_manager.cpp`（`AddOneObserver(CallVoiceAssistantManager)`、`MuteRinger`、`UpdateVoipCallState`）与 `call_status_manager.cpp`（`IsStartVoiceBroadcast`、`UpdateContactInfo`）接入主流程。

## Requirements

### Requirement: 播报与控制开关查询
系统 SHALL 由 `IsStartVoiceBroadcast` 首次查询 `BROADCAST_SWITCH` 后缓存（`isQueryedBroadcastSwitch`），仅首次真正下发查询。`IsSwitchOn` SHALL 按序判定：HiCar 车机在线（`DistributedCallManager::IsDistributedCarDeviceOnline`）恒返回 true（语音由 HiCar 控制）；前台帐号未解锁（`OsAccountManager::IsOsAccountVerified`）返回 false；否则经 `QueryValue`（`DataShareHelper`，KEYWORD 匹配）读取开关值，`SWITCH_TURN_OFF` 视为关。

#### Scenario: HiCar 在线
- **WHEN** 分布式车机设备在线时查询任一开关
- **THEN** 直接返回 true，不查询 datashare

#### Scenario: 帐号未解锁
- **WHEN** 前台系统帐号未通过验证时查询开关
- **THEN** 返回 false，不查询 datashare

#### Scenario: 播报开关缓存
- **WHEN** `IsStartVoiceBroadcast` 第二次及以后调用
- **THEN** 直接返回缓存的 `isBroadcastSwitchOn`，不再下发 datashare 查询

### Requirement: 语音助手 ability 连接管理
系统 SHALL 由 `ConnectAbility` 构造 `VoiceAssistantConnectCallback` 并经 `AbilityManagerClient::ConnectAbility` 拉起语音助手（HiCar 在线时 ability 元素切到 `HICAR_BUNDLE_NAME`，否则 `BUNDLE_NAME`，均为 `ABILITY_NAME`）；连接失败且播报开关开时 `VoiceAssistantRingSubscriber::Initial` 预订阅铃音广播、置 `isplay` 为开并发布 `connect_voice_assistant_ability_failed` 公共事件。连接成功后 `UpdateRemoteObject` SHALL 经队列校验 `nowCallId` 一致性（不一致直接 `DisconnectAbility` 回滚）后保存 `mRemoteObject` 并 `SendRequest`。`OnStopService` SHALL 依次 `DisconnectAbility`、`UnRegisterListenSwitchState`、`StopRingtone`、`VoiceAssistantRingSubscriber::Release`、发布 `on_stop_service` 事件并 `Release` 复位全部状态。

#### Scenario: 连接助手失败
- **WHEN** `ConnectAbility` 返回非 0 且 `isBroadcastSwitchOn` 为真
- **THEN** 预订阅铃音广播、置位播放标记并发布失败事件，铃音改由本端播放

#### Scenario: 过期连接回调
- **WHEN** `UpdateRemoteObject` 收到的 callId 与当前 `nowCallId` 不一致
- **THEN** 断开该 ability 连接，不更新 `mRemoteObject`

#### Scenario: 服务停止
- **WHEN** `OnStopService`（非析构场景）执行
- **THEN** 停止系统铃音、注销开关监听、释放铃音订阅并复位内部状态

### Requirement: 来去电状态触发
系统 SHALL 由 `CallStateUpdated` 仅处理 ACTIVE/DIALING/INCOMING/DISCONNECTED 四种状态并按 `GetContactInfo(callId)` 维护 `accountIds` 表：INCOMING 在免打扰（`CallObjectManager::IsNeedSilentInDoNotDisturbMode`）时不触发；VOIP off_hook（`nowVoipCallState` 为 `CALL_STATE_OFFHOOK`）时新来话先 `OnStopService`；来电时填充联系人/归属地（已有 ACTIVE 通话时 `dialOrCome` 改记 DIALING）；DIALING 置 `isQueryComplete` 为真后 `OnStartService`；ACTIVE 置零铃音量（`SetRingToneVolume(0.0f)`）、释放铃音订阅并复位播报开关缓存；DISCONNECTED 清理该 callId，若仍有 ACTIVE 通话则直接返回，若仍有 INCOMING 通话则对新来话重新 `SendRequest` 播报，否则 `SendRequest(lastInfo, false)` 后 `OnStopService` 收尾。`OnStartService` SHALL 在控制与播报开关全关时不拉起 ability；`mRemoteObject` 已存在时直接 `SendRequest`。

#### Scenario: 免打扰来话
- **WHEN** 来话转 INCOMING 且处于免打扰模式
- **THEN** 不触发语音助手服务启动

#### Scenario: 活跃通话中来话
- **WHEN** 已有 ACTIVE 通话时新来话转 INCOMING
- **THEN** 该来话记为 DIALING 场景处理，不作为新来话播报

#### Scenario: 通话接通
- **WHEN** 通话转 ACTIVE
- **THEN** 铃音量置零、铃音订阅释放、播报开关缓存复位

#### Scenario: 双开关全关
- **WHEN** `CONTROL_SWITCH` 与 `BROADCAST_SWITCH` 均为关时来话触发 `OnStartService`
- **THEN** 不连接语音助手 ability，直接返回

### Requirement: 来话信息 IPC 同步
系统 SHALL 由 `SendRequest` 在 `mRemoteObject` 有效且 `isQueryComplete`/`dialOrCome`/`numberLocation` 齐备时，经 `GetSendString` 组装 JSON（`dialOrCome`/`callStatus`/`callId`/`phoneNumber`/`isContact`/`contactName`/`sim`/`stopBroadcasting`/`location`）并以 `CHECK_CODE` 发起 `mRemoteObject->SendRequest`；应答经 `UpdateReplyData` 解析 `CONTROL_CHECK_RESULT`/`BROADCAST_CHECK_RESULT` 到 `controlCheck`/`broadcastCheck`。`UpdateContactInfo`/`UpdateNumberLocation` SHALL 异步提交队列，通话处于 DIALING 时不更新。应答后 SHALL 按检查结果决定：`controlCheck` 开且本端控制开关开时置 `isConnectService` 并 `RegisterListenSwitchState` 注册开关变化监听；播报检查开或 IPC 失败、且播报开关开、未请求停止、非去电场景时 `VoiceAssistantRingSubscriber::Initial` 置 `isplay` 为开。

#### Scenario: 信息不全时不出请求
- **WHEN** `SendRequest` 时 `isQueryComplete` 为假或 `numberLocation` 仍为 "default"
- **THEN** 不发起 IPC 请求

#### Scenario: 应答要求播报
- **WHEN** IPC 应答 `broadcastCheck` 为开且播报开关开且为来话场景
- **THEN** 铃音订阅初始化、`isplay` 置开，后续铃音广播将触发系统铃音播放

#### Scenario: 控制开关闭变化
- **WHEN** `VoiceAssistantSwitchObserver::OnChange` 检测 `CONTROL_SWITCH` 由开变关
- **THEN** 发布状态变化公共事件并置 `isControlSwitchOn` 为 false

### Requirement: 铃音让位与静默控制
系统 SHALL 由 `MuteRinger` 异步置零铃音量、释放铃音订阅、置 `isplay` 为关，并对当前 `nowCallId` 的信息置 `stopBroadcasting` 为 1 后发送停止播报 IPC 与 `stop_broadcast_event` 事件。`VoiceAssistantRingSubscriber::OnReceiveEvent` SHALL 仅响应 `CONTROL_SWITCH_STATE_CHANGE_EVENT` 且发布者为 `remote_object_send_request` 或 `connect_voice_assistant_ability_failed` 的事件：`isplay` 开且 `GetIsPlayRing()` 为真时先 `StopRingtone`，若 `NeedPlayVideoRing` 则携带 `VideoRingPath` 经 `CallAbilityReportProxy::ReportCallStateInfo` 上报后 `PlayRingtone`。

#### Scenario: 静默响铃
- **WHEN** `MuteRinger` 在来话播报期间执行
- **THEN** 铃音量置零、停止助手播报并清除播放标记

#### Scenario: 助手侧请求接管铃音
- **WHEN** 铃音广播事件携带 `IS_PLAY_RING` 开且本端 `GetIsPlayRing` 为真
- **THEN** 停止当前铃音后播放系统铃音（视频铃音路径场景先上报属性）

#### Scenario: 非目标发布者
- **WHEN** 广播事件发布者非 `remote_object_send_request`/`connect_voice_assistant_ability_failed`
- **THEN** 忽略该事件，不播放铃音

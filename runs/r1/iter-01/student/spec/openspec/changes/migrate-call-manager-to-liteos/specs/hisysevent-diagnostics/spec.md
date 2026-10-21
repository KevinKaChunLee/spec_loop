# Spec Delta

## MODIFIED Requirements

### Requirement: hidumper 服务信息打印

系统 SHALL 由 `CallManagerService::Dump(fd, args)`（`services/call_manager_service/src/call_manager_service.cpp`）保留入口与参数校验（fd<0 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，照抄），委托栈上构造的 `CallManagerDumpHelper::Dump(argsInStr, result)`（`services/hisysevent/src/call_manager_dump_helper.cpp`，文件与 Dump 项保留，design 决策 12）；liteOS 无 hidumper 服务，转储文本 SHALL 改走日志输出口径（design 决策 12：Dump 输出走日志；基线 `dprintf(fd, ...)` 与 `CALL_ERR_SERVICE_DUMP_FAILED` 写失败分支保留为日志失败注入语义）。`CallManagerDumpHelper::Dump` SHALL 先 `ShowHelp`（固定输出 -call_manager_info、-input_simulate/-output_simulate、-show_log_level/-set_log_level、-perf_dump 的 Usage 文本）再 `ShowCallManagerInfo`，恒返回 true（照抄）。`ShowCallManagerInfo` SHALL 依次输出全部保留项（照抄）：`CurrentTime`（经 `CallManagerService::GetBindTime()`，该函数每次调用刷新为当前毫秒时间戳，行为保持，design D9）、`SpendTime`（`GetStartServiceSpent()`）、`ServiceRunningState`、按 `SIM_SLOT_COUNT` 循环经 `WhetherHasSimCard(i)` 逐槽输出 "SlotId = i"（仅有卡的槽；查询出口改经 `stub/core_service_client` 桩的 `CoreServiceClient::GetInstance().HasSimCard`，design D4）、`CallState`、`RingingCallState`（`IsRinging(enabled)` 出参）、`HasCall`。不解析 args、不区分子命令（照抄）。

#### Scenario: 非法 fd
- **WHEN** 以 fd<0 调用 `CallManagerService::Dump`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`（照抄）

#### Scenario: 标准信息转储
- **WHEN** 以任意 args 调用 `Dump`
- **THEN** Usage 文本与 Ohos call_manager service 段（含时间/耗时/运行态/占卡槽列表/CallState/RingingCallState/HasCall）经日志输出口径产出，返回 `TELEPHONY_SUCCESS`（照抄项集）

#### Scenario: 无卡槽位不打印
- **WHEN** slotId=1 槽位的 `CoreServiceClient` 桩返回无 SIM 卡（桩默认态）
- **THEN** 转储文本不含 "SlotId = 1" 行（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增 Dump 项集用例（fd 校验、Usage+信息段日志断言、无卡槽过滤经桩）。

### Requirement: 通话状态与来电行为事件

系统 SHALL 由 `CallManagerHisysevent`（`services/hisysevent/src/call_manager_hisysevent.cpp`）保留行为事件写入语义，`HiSysEventWrite`/`HiWriteBehaviorEventPhoneUE` 出口 SHALL 改经 `stub/hisysevent_stub` 同名桩输出日志（函数签名不变，design D5）：`WriteCallStateBehaviorEvent(slotId, state, index)` 写事件 `CALL_STATE`，键 `SLOT_ID/STATE/INDEX_ID`（调用点 `services/telephony_interaction/src/call_status_callback.cpp` 保留，照抄）；`WriteIncomingCallBehaviorEvent(slotId, callType, callMode)` 写事件 `INCOMING_CALL`，键 `SLOT_ID/CALL_TYPE`，类型映射保留 IMS 语音→`IncomingCallType::IMS_VOICE_INCOMING`、IMS 视频→`IMS_VIDEO_INCOMING`、CS 语音→`CS_VOICE_INCOMING`——基线"CS 或卫星语音"中的 `SATELLITE_CALL_TYPE(5)` 分支随卫星通话删除（AGENTS「功能范围」卫星通话不支持；design D7 `satellite_call.cpp`/`satellite_call_control.cpp` 删除），其余组合记 "args is out of range" 日志并不写事件（照抄）；`WriteIncomingNumIdentityBehaviorEvent(markType, isBlock, blockReason)` 经模板 `HiWriteBehaviorEventPhoneUE` 以 PHONE_UE 域（`DOMAIN_PHONE_UE`）写事件 `CALL_INCOMING_NUM_IDENTITY`，固定键 PNAMEID="callmanager"、PVERSIONID=""、`MARK_TYPE/IS_BLOCK/BLOCK_REASON`（调用点 `services/spam_call/src/callback_stub_helper.cpp` 保留——骚扰/黄页识别逻辑保留，AGENTS「骚扰来电……暂不调用」出口桩化见 spam-call-identification/number-identity delta；照抄）。

#### Scenario: 状态回报触发 CALL_STATE
- **WHEN** 蜂窝通话状态变化经 `call_status_callback.cpp` 回调（桩注入）
- **THEN** `CALL_STATE` 行为事件携带 slotId、state、index 经维测桩日志输出（照抄键集）

#### Scenario: CS 来电事件
- **WHEN** callType 为 CS_CALL_TYPE(0) 且 callMode 为语音（基线含 SATELLITE_CALL_TYPE(5) 的组合）
- **THEN** `INCOMING_CALL` 事件 CALL_TYPE 值为 `CS_VOICE_INCOMING`；卫星类型分支随卫星通话删除，liteOS 上不可达（场景改写为 CS 单类型断言）

#### Scenario: 参数组合超界丢弃
- **WHEN** callType=IMS 且 callMode 既非语音也非视频
- **THEN** 仅记错误日志，不产生 `INCOMING_CALL` 事件（照抄）

#### Scenario: 号码识别结果上报
- **WHEN** 骚扰识别回调获得 markType/isBlock/blockReason
- **THEN** PHONE_UE 域 `CALL_INCOMING_NUM_IDENTITY` 事件经维测桩日志输出（不含号码字段，照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增行为事件键集断言（经维测桩）与卫星映射分支删除负向断言。

### Requirement: 四类故障事件与错误码映射

系统 SHALL 由 `CallManagerHisysevent` 保留四类故障事件语义，`HiWriteFaultEvent` 出口改经 `stub/hisysevent_stub` 同名桩输出日志（签名不变，design D5），公共键 `MODULE="CALL_MANAGER"` 与 `SLOT_ID` 照抄：`WriteDialCallFaultEvent(slotId, callType, videoState, errCode, desc)`→`CALL_DIAL_FAILED`（附 `CALL_TYPE/VIDEO_STATE/ERROR_TYPE/ERROR_MSG`，调用点 `call_manager_service.cpp` 保留——权限拒绝调用点已随权限校验移除删除，见 call-manager-service delta）；`WriteIncomingCallFaultEvent`→`CALL_INCOMING_FAILED`；`WriteAnswerCallFaultEvent(slotId, callId, videoState, errCode, desc)`→`CALL_ANSWER_FAILED`（附 `CALL_ID`）；`WriteHangUpFaultEvent(slotId, callId, errCode, desc)`→`CALL_HANGUP_FAILED`（附 `CALL_ID`）。写入前 SHALL 保留 `ErrorCodeConversion`（依次 `CallDataErrorCodeConversion`/`CallInterfaceErrorCodeConversion`/`TelephonyErrorCodeConversion` 把仓内错误码映射为 `CallErrorCode` 枚举填 ERROR_TYPE；映射失败原样写入 errCode，照抄）。`GetErrorDescription(errCode, desc)` SHALL 按错误类别生成固定描述（"NumberLegalityCheck failed"、"DialPolicy failed"、"CallRequestHandlerPtr_ or handler_ is nullptr"、"Send HANDLER_DIAL_CALL_REQUEST event failed" 等，照抄）。

#### Scenario: 拨号失败写故障
- **WHEN** `DialCall` 返回非 0 且 `GetErrorDescription` 命中
- **THEN** `CALL_DIAL_FAILED` 事件 ERROR_TYPE 为映射后 CallErrorCode，ERROR_MSG 为该描述（经维测桩日志断言，照抄）

#### Scenario: 未知错误码透传
- **WHEN** errCode 无法被三级映射命中
- **THEN** 事件 ERROR_TYPE 字段直接写入原始 errCode 数值（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增四类故障事件与三级映射矩阵用例（经维测桩断言键集与映射值）。

### Requirement: 拨号/来电/应答时延超时判定

系统 SHALL 由 `CallManagerHisysevent` 实例（`DelayedSingleton` 持有）保留三个起点与终点判定（照抄，事件写入经维测桩日志，design D5）：`SetDialStartTime()`（`DialCall` 入口调用）、`SetIncomingStartTime()`、`SetAnswerStartTime()`（`AnswerCall` 入口调用）；`JudgingDialTimeOut(slotId, callType, videoState)` 超过 `NORMAL_DIAL_TIME=500ms`、`JudgingIncomingTimeOut` 超过 `NORMAL_INCOMING_TIME=100ms`、`JudgingAnswerTimeOut(slotId, callId, videoState)` 超过 `NORMAL_ANSWER_TIME=300ms` 时，分别以 `CALL_ERROR_DIAL_TIME_OUT`、`CALL_ERROR_INCOMING_TIME_OUT`、`CALL_ERROR_ANSWER_TIME_OUT` 写调用对应的故障事件（描述附实际耗时；调用点 `services/call/src/call_status_manager.cpp` 等保留）。

#### Scenario: 拨号超时
- **WHEN** 自 `SetDialStartTime` 起超过 500ms 才到达判定点
- **THEN** 写 `CALL_DIAL_FAILED`，ERROR_TYPE 为 CALL_ERROR_DIAL_TIME_OUT（经维测桩日志，照抄）

#### Scenario: 未超时静默
- **WHEN** 应答在 300ms 内完成
- **THEN** `JudgingAnswerTimeOut` 不写任何事件（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增时延判定用例（桩时钟注入超时/未超时两态）。

### Requirement: VoIP 通话统计事件

系统 SHALL 由 `CallManagerHisysevent::WriteVoipCallStatisticalEvent(voipCallId, bundleName, uid, statisticalField)` 保留 STATISTIC 事件 `VOIP_CALL_STATISTICS` 写入语义（域为外部依赖头提供的 `DOMAIN_NAME` 常量，随依赖头平移；事件写入经维测桩日志，design D5）：基线 `ffrt::submit` 异步提交 SHALL 改经 `stub/eventhandler_stub` 桩 EventHandler 提交（design D8：ffrt 队列/任务→打桩 EventHandler，桩内同步执行、不新增线程）；`GetAppIndexByBundleName`（基线经 `SystemAbilityManager` 取 `BUNDLE_MGR_SERVICE_SYS_ABILITY_ID` 的 `IBundleMgr` 调 `GetNameAndIndexForUid` 反查 appIndex）属 ability 查询调用点，SHALL 以 todo 占位桩化（同 getBundleInfo 处置，design D6 ability 查询类），桩默认不可用时 appIndex 保持 -1（照抄基线 SA 缺失分支），随后携带 `CALL_ID/BUNDLE_NAME/STATISTICAL_FIELD/APP_INDEX` 写入。callId 重载 SHALL 保留先经 `CallControlManager::GetOneCallObject` 判空且 callType 必须为 TYPE_VOIP，再以 `reinterpret_cast<VoIPCall*>` 取 voipCallId/bundleName/uid 转调字符串版本（照抄；调用点 `services/telephony_interaction/src/voip_call_connection.cpp`（"HungupByCallmanager"）与 `services/call/src/call_control_manager.cpp`（"MtBannerAnswer" 等）保留）。

#### Scenario: 非 VoIP 通话不统计
- **WHEN** callId 对应对象为空或 callType 非 TYPE_VOIP
- **THEN** 直接返回，不写事件（照抄）

#### Scenario: 异步补齐 appIndex
- **WHEN** 写入时 appIndex 反查桩可用（配置态）
- **THEN** 事件 APP_INDEX 为反查结果；桩默认不可用态时 APP_INDEX 为 -1（照抄基线 BundleMgr 缺失分支语义）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系，含 `zero_branch4_test.cpp`/`zero_branch6_test.cpp` 的 hisysevent 用例面）新增 VoIP 统计用例（TYPE_VOIP 判定矩阵、桩 EventHandler 提交断言、APP_INDEX 两态）。

### Requirement: VoIP NDK 侧事件写入口

系统 SHALL 保留 `NativeCallManagerHisysevent::WriteVoipCallEvent(callId, bundleName, scenario, errCode, errorMsg, callType, callState, callDirection)`（`frameworks/native/src/native_call_manager_hisysevent.cpp`，文件未列入 design D7 被删文件表、保留；函数签名不变），事件写入 SHALL 改经 `stub/hisysevent_stub` 桩输出日志（design D5；Scenario 枚举值随接口签名平移）。基线唯一调用方 `voip_call_manager_proxy.cpp`（VoIP IPC 连接失败路径，`Scenario::VOIP_PROXY_IPC_CONNECTTING`）随 `VoipCallManagerProxy` 删除（native-client-api delta：命令族改 `stub/voip_call_client` 桩出口，对端缺失打维测语义在桩失败路径保留）；liteOS 上真实对端待畅连通话接入后由 voip 对接层挂接（AGENTS「暂不支持 VOIP……依赖后续跟 meetime 畅连通话」），写入口不因暂无调用而丢弃（AGENTS：代码按功能实现，不因无外部接口而丢弃功能）。

#### Scenario: NDK VoIP 调用结果上报
- **WHEN** voip 桩失败路径（默认不可用态）或后续畅连对接层触发 `WriteVoipCallEvent`
- **THEN** 以 callId/bundleName/scenario/err/callType/callState/callDirection 组装事件并经维测桩日志输出（照抄字段集）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增 `WriteVoipCallEvent` 直调用例（字段集经维测桩断言）。

### Requirement: 事件隐私约束

系统 SHALL 保证本能力写入的全部事件（经维测桩日志输出后同样适用）不携带明文电话号码：故障/行为事件的字段集合仅有 `MODULE/SLOT_ID/INDEX_ID/STATE/CALL_ID/CALL_TYPE/VIDEO_STATE/ERROR_TYPE/ERROR_MSG/MARK_TYPE/IS_BLOCK/BLOCK_REASON/PNAMEID/PVERSIONID/BUNDLE_NAME/STATISTICAL_FIELD/APP_INDEX` 等标识与枚举值（结论照抄）；`CALL_INCOMING_NUM_IDENTITY` 只携带识别结果不携带号码本身；`CallManagerDumpHelper` 的文本输出（日志形态）同样不含任何号码或联系人字段；话单/号码展示由 `core_service` 域的 CALL_STATE 系事件处理，不在本仓面（照抄）。日志隐私红线保持（proposal Impact「保持不变」条：号码/联系人名不进日志）。

#### Scenario: 故障事件字段巡检
- **WHEN** 任一 fault/behavior 事件按声明的键集合打包（经维测桩日志输出）
- **THEN** 键集合内不存在 phone number 类字段（照抄）

#### Scenario: dump 文本巡检
- **WHEN** `ShowCallManagerInfo` 生成转储文本（日志形态）
- **THEN** 文本只含服务/状态布尔与枚举数值，无号码（示例号码 unknown 不出现于任何事件场景，照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增隐私巡检用例（全部事件键集与 dump 日志文本无号码断言）。

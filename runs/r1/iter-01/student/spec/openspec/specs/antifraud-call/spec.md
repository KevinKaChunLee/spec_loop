# Antifraud Call Specification

## Purpose
描述目标仓中现有的防诈检测能力：通话激活时（系统参数 `const.telephony.antifraud.supported`，常量 `ANTIFRAUD_FEATURE`，运行时开关而非编译宏）按条件对通话启动防诈语音检测，检测由 `AntiFraudAdapter` 经 `dlopen("libanti_fraud_service_client.so")` + `dlsym` 调用外部防诈算法库完成；检测结果经监听器回调记录并回传 call 状态（`antiFraudState` extraParams），判定为诈且用户同意改进计划（设置项 `spamshield_call_live_report`）时，先由 `AnonymizeAdapter`（`dlopen("libdia_sdk.z.so")`，`DIA_*` 符号）对检测文本脱敏，再经 `AntiFraudCloudService` + `HsdrHelper`（连接 `com.hmos.hsdr` 的 HSDR 服务扩展）完成加密/签名（UCS）与云侧 HTTPS 上传（`com.cloud.afs.ROOT`）。开关查询走 DataShare 设置数据库（`USER_SETTINGSDATA_URI`，键 `spamshield_call_live_detection` / `spamshield_call_live_report`）。落点：`services/antifraud/src/{anonymize_adapter,antifraud_adapter,antifraud_cloud_service,antifraud_hsdr_helper,antifraud_service}.cpp` 及 `services/antifraud/antiinclude/` 下的外部头副本；启动/停止入口在 `CallStatusManager`。本能力无专属编译宏（rg 核实：`services/antifraud/` 内仅 `__cplusplus` 保护，五个源文件在 `callmanager.gni` 无条件编入）。

## Requirements

### Requirement: 检测启动条件判定
系统 SHALL 在 `CallStatusManager::ActiveHandle` 中读取系统参数 `ANTIFRAUD_FEATURE`（`const.telephony.antifraud.supported`，默认 true），开启时调用 `SetupAntiFraudService`：仅在主用户空间（`MAIN_USER_SPACE`）、号码标记非 `MarkType::MARK_TYPE_FRAUD` / `MARK_TYPE_YELLOW_PAGE` / `MARK_TYPE_ENTERPRISE`、非联系人（`IsContactPhoneNum` 内经 `QueryCallerInfo` 查询）、`AntiFraudService::IsAntiFraudSwitchOn()`（设置键 `spamshield_call_live_detection`）且无进行中检测（`GetAntiFraudSlotId` / `GetAntiFraudIndex` 均为 -1）时，记录 `SetAntiFraudSlotId` / `SetAntiFraudIndex` 并以 `ffrt::submit` 异步调用 `AntiFraudService::StartAntiFraudService`；启动失败 SHALL 回滚槽位/索引为 -1。`StartAntiFraudService` SHALL 先经 `CheckAntiFraudService`（`AntiFraudAdapter::CheckAntiFraud`）预检，再核对通话是否已结束（与 `CallStatusManager` 记录的槽位/索引比对），通过后才发起检测并 `TriggerAntiFraud(ANTIFRAUD_STATE_STARTED)`、`InitParams` 复位参数。

#### Scenario: 条件齐备启动检测
- **WHEN** 通话激活且上述条件全部满足
- **THEN** `StartAntiFraudService` 发起检测并把防诈状态置为 `ANTIFRAUD_STATE_STARTED`

#### Scenario: 已有通话在检则跳过
- **WHEN** `GetAntiFraudSlotId()` / `GetAntiFraudIndex()` 已被占用
- **THEN** 本通话不启动新检测

#### Scenario: 通话已结束
- **WHEN** 异步启动时槽位/索引与当前激活通话不匹配
- **THEN** 返回 -1，不发起检测

### Requirement: 防诈算法库 dlopen 适配器
系统 SHALL 由 `AntiFraudAdapter` 维护 `libAntiFraud_`（`dlopen("libanti_fraud_service_client.so", RTLD_LAZY)`，`GetLibAntiFraud` 惰性加载、`ReleaseAntiFraud` 释放），并在三个操作上 `dlsym` 命中外部符号：`AntiFraudVoiceCheck`（`CheckAntiFraud(phoneNum)` 预检）、`AntiFraudVoiceDetect`（`DetectAntiFraud(listener)` 启动检测，携带 `AntiFraudDetectResListenerImpl`）、`StopAntiFraudVoiceDetect`（`StopAntiFraud()`）。库缺失或符号缺失 SHALL 返回 -1 并中止对应流程。该 dlopen 是独立移植桩化出口。

#### Scenario: 库不存在
- **WHEN** `dlopen` 返回空句柄
- **THEN** `CheckAntiFraud` / `DetectAntiFraud` / `StopAntiFraud` 均返回 -1

#### Scenario: 启动检测携带监听器
- **WHEN** `DetectAntiFraud` 以 `AntiFraudService::AntiFraudDetectResListenerImpl`（保存号码、槽位、索引）调用 `AntiFraudVoiceDetect`
- **THEN** 外部库持有监听器并在检测完成后回调 `HandleAntiFraudDetectRes`

### Requirement: 检测停止与迟到结果丢弃
系统 SHALL 由 `CallStatusManager::StopAntiFraudDetect`（断开时）与 `CallStatusManager::HandleCeliaCall`（小艺通话接管时）在槽位/索引匹配时调用 `AntiFraudService::StopAntiFraudService` 并复位 `SetAntiFraudSlotId(-1)` / `SetAntiFraudIndex(-1)`；`StopAntiFraudService` SHALL 调 `StopAntiFraud` 停检并记录 `stoppedSlotId_` / `stoppedIndex_`，`RecordDetectResult` 比中停止记录时 SHALL 丢弃该迟到结果并复位停止记录为 -1 后返回。

#### Scenario: 停止后丢弃迟到结果
- **WHEN** 回调结果的槽位/索引等于 `stoppedSlotId_` / `stoppedIndex_`
- **THEN** 结果不记录、状态不更新

### Requirement: 检测结果记录与状态回传
系统 SHALL 在 `AntiFraudService::RecordDetectResult` 中把外部回调的 `OHOS::AntiFraudService::AntiFraudResult`（字段 `errCode` / `result` / `modelVersion` / `fraudType` / `text` / `pvalue`，类型见 `antiinclude/anti_fraud_service_client_type.h`）写入成员（`fraudDetectErr_` / `isResultFraud_` / `fraudDetectVersion_` / `fraudDetectType_` / `fraudDetectText_` / `fraudDetectProb_`），并把状态置为 `AntiFraudState::ANTIFRAUD_STATE_RISK`（欺诈）或 `ANTIFRAUD_STATE_FINISHED`（正常），经 `callStatusManagerPtr_->TriggerAntiFraud(antiFraudState)` 回传；`CallStatusManager::TriggerAntiFraud` SHALL 在通话明细索引命中后把状态写入 extraParams（`UpdateAntiFraudState`，键 `antiFraudState`），状态为 RISK / FINISHED 时复位占用标记（`SetAntiFraudSlotId(-1)` / `SetAntiFraudIndex(-1)`），若通话当前 ACTIVE 则重新 `UpdateCallState(CALL_STATUS_ACTIVE)` 通知 UI 刷新。

#### Scenario: 判定为欺诈风险
- **WHEN** `result` 为 true
- **THEN** 状态置 `ANTIFRAUD_STATE_RISK`，call 对象 extraParams 的 `antiFraudState` 更新为 2

#### Scenario: 通话已不存在
- **WHEN** `TriggerAntiFraud` 找不到索引对应的 call 对象
- **THEN** 仅做占用标记复位，不更新 extraParams

### Requirement: 防诈开关 DataShare 查询
系统 SHALL 由 `AntiFraudService::CreateDataShareHelper(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID, USER_SETTINGSDATA_URI)`（经 `SystemAbilityManagerClient` 取远端后 `DataShare::DataShareHelper::Creator`）创建设置数据库助手，`IsSwitchOn(switchName)` 用 `DataSharePredicates` 的 `KEYWORD` 等值查询 `USER_SETTINGSDATA_SECURE_100` 数据，取 `VALUE` 列，值转 int 等于 1 视为开。该 DataShare 出口是移植时的独立桩化点。

#### Scenario: 实时检测开关
- **WHEN** 查询键 `ANTIFRAUD_SWITCH`（`spamshield_call_live_detection`）
- **THEN** `IsAntiFraudSwitchOn` 返回数据库值是否为 1

#### Scenario: 助手创建失败
- **WHEN** SA 管理器或远端对象获取失败
- **THEN** `IsSwitchOn` 返回 false，视为关闭

### Requirement: 检测文本脱敏（anonymize 适配器）
系统 SHALL 由 `AnonymizeAdapter` 维护 `libAnonymize_`（`dlopen("libdia_sdk.z.so", RTLD_LAZY)`），并按符号 `DIA_InitConfig` / `DIA_SetRule` / `DIA_CreateAnonymize` / `DIA_IdentifyAnonymize` / `DIA_ReleaseConfig` / `DIA_ReleaseAnonymize` / `DIA_ReleaseOutputData` 封装（`antiinclude/dia_interface_c.h` 等 DIA C 接口）。`AntiFraudService::AnonymizeText` SHALL 依次：`InitConfig`；经 `AddRuleToConfig` 以选择键 `SELECT_RULE`（长度 `SELECT_RULE_LENGTH`=11）注册规则 `PRC`、`CHINA_RESIDENT_PASSPORT`、`MILITARY_IDENTITY_CARD_NUMBER`、`BANK_CARD_NUMBER`、`PERMIT_LAND_TO_HM`、`PERMIT_LAND_TO_TW`、`PERMIT_HM_TO_LAND`、`PERMIT_TW_TO_LAND`、`BIRTH_CERTIFICATE`、`SEAFARER_PASSPORT`、`POLICE_OFFICER_CARD`（其中 `CHINA_RESIDENT_PASSPORT`、`PERMIT_HM_TO_LAND`、`PERMIT_TW_TO_LAND`、`POLICE_OFFICER_CARD` 置 `rule.isOpenKeywords=true`）；`CreateAnonymize`；`IdentifyAnonymize` 处理 `fraudDetectText_` 并以输出串替换之；最后 `ReleaseConfig` / `ReleaseAnonymize` / `ReleaseOutputData`。该 dlopen 是独立移植桩化出口；本能力不处理联系人脱敏（脱敏对象仅为检测文本 `fraudDetectText_`）。

#### Scenario: 证件信息脱敏
- **WHEN** 检测文本包含命中所选规则的证件内容
- **THEN** 上报前文本被替换为脱敏结果

#### Scenario: DIA 库缺失
- **WHEN** `dlopen("libdia_sdk.z.so")` 失败或任一 `dlsym` 为空
- **THEN** `AnonymizeText` 非 0 返回，`RecordDetectResult` 终止上报

### Requirement: 云上报条件与负载生成
系统 SHALL 仅在 `isResultFraud_` 且 `IsUserImprovementPlanSwitchOn()`（设置键 `USER_IMPROLAN_SWITCH`，`spamshield_call_live_report`）为真时执行 `AnonymizeText` 脱敏并以脱敏后文本替换 `AntiFraudResult.text` 后构造 `AntiFraudCloudService(phoneNum)->UploadPostRequest(fraudResult)`。上传负载 `AntiFraudCloudService::GeneratePayload` SHALL（cJSON 组装）包含字段：`modelCaller`="com.hsdr"、随机 `reqNo`、常量 `calleeId`="15564984"、`osType`="1"、`serviceType`="00000002"、`callerNum`=主叫号码（隐私字段，示例以 unknown 表示）、`markerId`="11"、`romVer`（系统参数 `const.product.software.version` 截到 `(` 前，`GetSubstringBeforeSymbol`）、`modelVer`、`modelScore`=`pvalue`、`modelDecision`=`fraudType`。

#### Scenario: 改进计划关闭则不上报
- **WHEN** `spamshield_call_live_report` 为 0
- **THEN** 检测结果仅本地记录，不发起云上报

#### Scenario: 负载组装
- **WHEN** 触发上报
- **THEN** 负载 JSON 含模型版本/分数/决策与主叫号码，随机 `GenerateRandomString(REQUEST_NO_LENGTH=10)` 生成 reqNo

### Requirement: HSDR 服务的连接管理
系统 SHALL 由 `HsdrHelper`（`DECLARE_DELAYED_REF_SINGLETON`）维护到 `com.hmos.hsdr` / `HSDRService` 的 AA ServiceExtension 连接：`ConnectHsdr(connectedCallback)` 创建 `AAFwk::Want`（action "NO_PUSH"，`HSDR_USERID`=100）经 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` 连接，已有存活连接（`HsdrConnection::IsAlive`）则直接回调复用；`DisconnectHsdr` 调 `DisconnectAbility` 并清空 `connection_`。`HsdrConnection` SHALL 在 `OnAbilityConnectDone` 校验 resultCode 与回调非空后存储远端并触发 `connectedCallback_`，在 `OnAbilityDisconnectDone` 清空远端（resultCode==`UNEXPECT_DISCONNECT_CODE`(-1) 记异常断连）。该 AA 连接是独立移植桩化出口。

#### Scenario: 复用已有连接
- **WHEN** `ConnectHsdr` 时 `connection_` 存活
- **THEN** 直接用旧连接的 `GetAbilityProxy()` 回调，不重复连接

#### Scenario: 连接失败
- **WHEN** `ConnectServiceExtensionAbility` 返回非 0
- **THEN** 记错误码并返回，`connection_` 置空

### Requirement: UCS 同步请求（加密与签名）
系统 SHALL 由 `HsdrProxy::RequestHsdrServiceSync`（`HsdrInterface` 描述符 `OHOS.Security.HSDR`，code 取 `HsdrCommands::COMMAND_UCS_REQUEST`=3，`serviceName`="com.hmos.hsdr.antifraud"，parcel：serviceName、requestId、body 的 String16Vector）提供同步通道。`AntiFraudCloudService::UploadPostRequest` SHALL 以 `std::weak_ptr` 守护 + `mutex_` / `cv_` / `isSettled_` 同步等待：第一个 `ConnectHsdr` 回调里 `EncryptSync`（`GenerateUcsRequestBody(UcsMethod::Encrypt, Base64(metaData))`，`EncodeBase64`）→ `ProcessEncryptResult` 解析 `ak` / `data`；`GetAuthSync` 以待签名串 "POST&" + `UPLOAD_MODEL_PATH`("\/rms\/v1\/antiFraud\/upload-model-result") + "&&" + metaData + "&ak=..." + "&timestamp=..." 调 `UcsMethod::Sign` → `ProcessSignResult`，拼出 auth 头 `EXT-CLOUDSOA-HMAC-SHA256 ak="...",timestamp=...,signature="..."`；等待超时（`COMMON_TIME_OUT`=5000ms）或 auth 为空 SHALL `DisconnectHsdr` 并返回失败。

#### Scenario: 加密签名同步完成
- **WHEN** 两次 UCS 同步请求均成功返回 ak 与 signature
- **THEN** 拿到完整 auth 头并进入云上传阶段

#### Scenario: 等待 auth 超时
- **WHEN** `cv_.wait_for` 到 5000ms 仍未 `isSettled_`
- **THEN** `UploadPostRequest` 返回 false 并断开 HSDR 连接

### Requirement: 云侧异步上传
系统 SHALL 由 `AntiFraudCloudService::ConnectCloudAsync`（code `HsdrCommands::COMMAND_CLOUD_CONNECT`=2，`serviceName`="com.cloud.afs.ROOT"）发起异步上传：`GenerateHeadersMap` 组头（`Authorization`=auth、`X-Request-ID`=`GetDeviceSerial()`（`GetSerial()` 失败回退 `GenerateRandomString(SERIAL_NUM_LEN=16)`）、`Content-Digest`=`CalculateDigest`（OpenSSL SHA256 十六进制、小写填充）、`down-algo`="AES-GCM"、`X-OS-Version`=`system::GetParameter("const.ohos.fullname")`、`Content-Type`=multipart boundary）；body 为 multipart（随机 `BOUNDARY_LENGTH`=32 边界，`meta-data` 段为负载 JSON，`file-data` 段为脱敏文本）；`GenerateRequestJson` 组出含 method/path/headers/timeout（`COMMON_TIME_OUT`=5000）的请求 JSON，携带 `HsdrCallbackStub`（描述符 `OHOS.Security.CloudConnectCallback`，`OnRemoteRequest` 校验 descriptor、读 requestId（与本地期望不一致仅告警）、拼接 body 字符串后分发 `onResponse_` / `onError_`）经 `RequestHsdrServiceAsync` 发送。响应/错误回调内 SHALL `DisconnectHsdr`。Base64（`base64.h`）、SHA256、系统参数接口均为移植桩化出口。

#### Scenario: 上传成功
- **WHEN** 云侧经回调桩返回响应
- **THEN** 记日志 body 并断开 HSDR 连接

#### Scenario: 回调桩读数据失败
- **WHEN** descriptor 不匹配或 String16Vector 读取失败
- **THEN** `onError_` 收到对应错误码（`CALLMANAGER_HSDR_ERR_PERMISSION_ERR` / `CALLMANAGER_HSDR_ERR_READ_DATA_FAIL`）
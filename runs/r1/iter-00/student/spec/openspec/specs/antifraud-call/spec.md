# 防诈（Antifraud Call） Specification

## Purpose
描述来电防诈骗实时检测能力的基线行为：对满足条件的来电启动防诈语音检测、接收检测结果并联动通话状态、对检测文本做匿名化后经 HSDR 云通道上报。源码落点：`telephony_call_manager/services/antifraud/{antiinclude,include,src}`（`antifraud_adapter.cpp`、`antifraud_service.cpp`、`antifraud_cloud_service.cpp`、`antifraud_hsdr_helper.cpp`、`anonymize_adapter.cpp`），调用方为 `telephony_call_manager/services/call/src/call_status_manager.cpp` 的 `SetupAntiFraudService`/`StopAntiFraudDetect`/`HandleCeliaCall`。该能力无专属编译宏：源文件无条件列入 `callmanager.gni` 的 `call_manager_sources`。

## Requirements

### Requirement: 防诈检测启停
系统 SHALL 由 `CallStatusManager::SetupAntiFraudService` 在主帐号空间、来电标记非 `MARK_TYPE_FRAUD`/`MARK_TYPE_YELLOW_PAGE`/`MARK_TYPE_ENTERPRISE`、非联系人号码且设置项 `spamshield_call_live_detection`（`ANTIFRAUD_SWITCH`）开启时，经 ffrt 异步调用 `AntiFraudService::StartAntiFraudService`；`AntiFraudAdapter` 通过 `dlopen("libanti_fraud_service_client.so")` 与 `dlsym` 解析 `AntiFraudVoiceCheck`/`AntiFraudVoiceDetect`/`StopAntiFraudVoiceDetect` 完成校验、检测与停止；通话结束（`StopAntiFraudDetect`）或 Celia 通话开始（`HandleCeliaCall`）时 MUST 调用 `StopAntiFraudService` 并复位 `antiFraudSlotId_`/`antiFraudIndex_`。
#### Scenario: 满足条件启动检测
- **WHEN** 来电满足标记/联系人/开关/主帐号四项条件且 `AntiFraudVoiceCheck` 返回 0
- **THEN** `AntiFraudDetectResListenerImpl` 被注册并 `AntiFraudVoiceDetect` 启动检测，状态置为 `ANTIFRAUD_STATE_STARTED`
#### Scenario: 检测中已有检测
- **WHEN** `GetAntiFraudSlotId`/`GetAntiFraudIndex` 已指向在检通话
- **THEN** 不为本次来电启动新检测
#### Scenario: 库缺失不检测
- **WHEN** `dlopen("libanti_fraud_service_client.so")` 返回空
- **THEN** `CheckAntiFraud` 返回 -1，`StartAntiFraudService` 返回该错误码，检测状态保持不变

### Requirement: 检测结果状态联动
系统 SHALL 由 `AntiFraudService::RecordDetectResult` 在收到 `HandleAntiFraudDetectRes` 回调时记录 `errCode`/`result`/`modelVersion`/`fraudType`/`text`/`pvalue`，并将状态置为 `ANTIFRAUD_STATE_RISK`（命中诈骗）或 `ANTIFRAUD_STATE_FINISHED`（未命中），随后经 `CallStatusManager::TriggerAntiFraud` 将 `antiFraudState` 写入对应通话的 extraParams；已停止的检测（`stoppedSlotId_`/`stoppedIndex_` 匹配）MUST NOT 记录结果。
#### Scenario: 命中诈骗
- **WHEN** 检测回调 `AntiFraudResult.result == true`
- **THEN** 状态置为 `ANTIFRAUD_STATE_RISK` 并经 `TriggerAntiFraud` 更新通话 extraParams 的 `antiFraudState`
#### Scenario: 检测已停止后回调到达
- **WHEN** 回调携带的 slotId/index 与 `StopAntiFraudService` 记录的停止值一致
- **THEN** 丢弃该结果，不更新状态、不触发上报

### Requirement: 检测文本匿名化
系统 SHALL 在命中诈骗且设置项 `spamshield_call_live_report`（`USER_IMPROPLAN_SWITCH`）开启时，由 `AnonymizeText` 经 `AnonymizeAdapter`（`dlopen("libdia_sdk.z.so")`、`DIA_InitConfig`/`DIA_SetRule`/`DIA_CreateAnonymize`/`DIA_IdentifyAnonymize`）对 `fraudDetectText_` 匿名化：注册 `PRC`、`CHINA_RESIDENT_PASSPORT`、`BANK_CARD_NUMBER` 等 11 类规则，匿名化结果回填 `fraudDetectText_` 后进入云端上报；匿名化失败 MUST NOT 上报。
#### Scenario: 匿名化成功
- **WHEN** 命中诈骗且 `spamshield_call_live_report` 为 1，`DIA_IdentifyAnonymize` 返回 0
- **THEN** `fraudDetectText_` 被替换为匿名化文本并调用 `AntiFraudCloudService::UploadPostRequest`
#### Scenario: 匿名化库缺失
- **WHEN** `dlopen("libdia_sdk.z.so")` 返回空
- **THEN** `AnonymizeText` 返回非 0，放弃云端上报

### Requirement: HSDR 云端上报
系统 SHALL 由 `AntiFraudCloudService::UploadPostRequest` 经 `HsdrHelper` 连接 HSDR 扩展（bundle `com.hmos.hsdr`、ability `HSDRService`），先以 `HsdrProxy::RequestHsdrServiceSync`（`UcsMethod::Encrypt`/`UcsMethod::Sign`）完成负载加密与鉴权（等待上限 `COMMON_TIME_OUT` 5000ms，超时即断开并放弃），再异步将检测负载（cJSON 组装 `modelCaller`/`reqNo`/`callerNum`/`modelVer`/`modelScore`/`modelDecision` 等字段）上报云端（路径 `/rms/v1/antiFraud/upload-model-result`）；鉴权失败或超时 MUST NOT 发起上报。
#### Scenario: 鉴权超时
- **WHEN** 连接 HSDR 后 5000ms 内未获得鉴权结果
- **THEN** `UploadPostRequest` 返回 false 并断开 HSDR 连接，不发起云端上报
#### Scenario: 鉴权成功异步上报
- **WHEN** `EncryptSync`/`GetAuthSync` 均成功取得非空 auth
- **THEN** 经 `ConnectCloudAsync` 发起异步上报，`UploadPostRequest` 返回 true

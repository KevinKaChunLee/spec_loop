# 防诈通话检测（antifraud-call）Specification

## Purpose
描述 `telephony_call_manager/services/antifraud/` 的防诈模块组：`AntiFraudService`（检测编排与状态联动）、`AntiFraudAdapter`（dlopen `libanti_fraud_service_client.so`）、`AnonymizeAdapter`（dlopen `libdia_sdk.z.so` 脱敏）、`AntiFraudCloudService`（经 HSDR 扩展上云）、`HsdrHelper`（HSDR 连接与加密签名）；外部库头文件在 `services/antifraud/antiinclude/`（`AntiFraudDetectResListener` 等）。该模块组无独有编译开关，启用与否由运行时系统参数与 DataShare 开关决定。

## Requirements

### Requirement: 防诈检测编排
系统 SHALL 由 `AntiFraudService::IsAntiFraudSwitchOn` 经 DataShare（`USER_SETTINGSDATA_URI = "datashare:///com.ohos.settingsdata/entry/settingsdata/USER_SETTINGSDATA_SECURE_100?Proxy=true"`）查开关 `ANTIFRAUD_SWITCH = "spamshield_call_live_detection"`（value == "1" 为开）；`StartAntiFraudService(phoneNum, slotId, index)` 先 `CheckAntiFraudService`→`AntiFraudAdapter::CheckAntiFraud`，再校验 slotId/index 与 `CallStatusManager::GetAntiFraudSlotId()/GetAntiFraudIndex()` 一致后创建 `AntiFraudDetectResListenerImpl(phoneNum, slotId, index)` 调 `DetectAntiFraud(listener)` 并置 `ANTIFRAUD_STATE_STARTED` 后 `TriggerAntiFraud`。
#### Scenario: 检测开关关闭
- **WHEN** `spamshield_call_live_detection` 的 DataShare 值非 "1"
- **THEN** 不启动防诈语音检测

### Requirement: 检测结果状态联动
系统 SHALL 由 `AntiFraudService::RecordDetectResult`：若 `SetStoppedSlotId/SetStoppedIndex` 匹配则丢弃迟到结果；否则记录结果并把状态置 `ANTIFRAUD_STATE_RISK` 或 `ANTIFRAUD_STATE_FINISHED` 后 `TriggerAntiFraud(antiFraudState_)`；`isResultFraud_ && IsUserImprovementPlanSwitchOn()`（`USER_IMPROPLAN_SWITCH = "spamshield_call_live_report"`）时先 `AnonymizeText()` 脱敏再 `AntiFraudCloudService(resultPhoneNum)->UploadPostRequest(fraudResult)`。
#### Scenario: 检出诈骗风险
- **WHEN** 检测结果为诈骗（`isResultFraud_` 为真）
- **THEN** 状态置 `ANTIFRAUD_STATE_RISK`，UI 侧号码标记置 `MarkType::MARK_TYPE_FRAUD_RISK` 并以 "antiFraudState" extraParams 上报

### Requirement: 防诈库与脱敏库 dlopen
系统 SHALL 由 `AntiFraudAdapter` 经 `dlopen("libanti_fraud_service_client.so", RTLD_LAZY)` + `dlsym` 绑定 `AntiFraudVoiceCheck/AntiFraudVoiceDetect/StopAntiFraudVoiceDetect`（typedef `PfnAntiFraudVoiceCheck/PfnAntiFraudVoiceDetect/PfnStopAntiFraudVoiceDetect`）；由 `AnonymizeAdapter` 经 `dlopen("libdia_sdk.z.so", RTLD_LAZY)` + `dlsym` 绑定 `DIA_InitConfig/DIA_SetRule/DIA_CreateAnonymize/DIA_IdentifyAnonymize/DIA_ReleaseConfig/DIA_ReleaseAnonymize/DIA_ReleaseOutputData`。
#### Scenario: 脱敏规则下发
- **WHEN** 上云前执行 `AnonymizeText()`
- **THEN** 以 key `"SELECT_RULE"`（`SELECT_RULE_LENGTH = 11`）对身份证/银行卡等 11 类规则开启脱敏后识别替换

### Requirement: HSDR 加密上云
系统 SHALL 由 `HsdrHelper::ConnectHsdr` 连接 `HSDR_BUNDLE_NAME = "com.hmos.hsdr"` / `HSDRService`（`HsdrProxy : IRemoteProxy<HsdrInterface>`，descriptor `u"OHOS.Security.HSDR"`），`AntiFraudCloudService::UploadPostRequest` 两段式：先 `EncryptSync`（`UCS_SERVICE_NAME = "com.hmos.hsdr.antifraud"`，`UcsMethod::Encrypt`）与 `GetAuthSync`（`UcsMethod::Sign`，auth 头 `EXT-CLOUDSOA-HMAC-SHA256`，路径 `UPLOAD_MODEL_PATH = "/rms/v1/antiFraud/upload-model-result"`），再 `ConnectCloudAsync`（`CLOUD_CONNECT_SERVICE_NAME = "com.cloud.afs.ROOT"`，multipart 脱敏文本）完成上传。
#### Scenario: HSDR 连接超时
- **WHEN** `cv_.wait_for` 5000 毫秒未收到 HSDR 回调
- **THEN** 上传放弃并按失败处理

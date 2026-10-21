# Tasks

门禁命令（本 change 的 must-pass 验收，各任务组完成条件之一）：

```
cd test && bash build.sh all
# 门禁标准：全部 must-pass 套件 rc=0 且 0 FAILED，输出 MUST-PASS GATE: PASS
# 套件集合随任务组 3 收敛为：sanity_test、liteos_stub_test、
#   tel_call_manager_zero2_gtest、tel_call_manager_zero5_gtest、tel_call_manager_special2_test
```

## 1. 基线固定与整棵拷贝

- [ ] 1.1 将 `telephony_call_manager/` 整棵拷贝为 `telephony_call_manager_mini/`（剔除 `test/fuzztest/`），用 `diff -rq` 抽查确认目录结构与文件命名与基线一致
- [ ] 1.2 将 `test/base/telephony/call_manager` 符号链接改指 `telephony_call_manager_mini/`，执行门禁确认 8 套件在未裁剪副本上仍全部 PASS（拷贝完整性验证；基线目录确认零改动）
- [ ] 1.3 must-pass 门禁仍为 PASS（`bash build.sh all` 输出 `MUST-PASS GATE: PASS`）

## 2. stub/ 桩层落地（`telephony_call_manager_mini/stub/`）

- [ ] 2.1 实现外部模块客户端单例桩（`CellularCallClient`/`CoreServiceClient`/`CellularDataClient`/`SmsClient`/`TelephonyCustClient`，方法名镜像基线 `ICellularCall`/`ICoreService` 等接口），验证 `liteos_stub_test` 新增冒烟用例 `Stub_XxxClient_GetInstance_ReturnsDefault` 全绿
- [ ] 2.2 实现 EventHandler 与 ffrt 兼容桩（`ffrt::submit`/`submit_h`/`queue`/`mutex` → 打桩 EventHandler；`PostTask` 延时任务带可注入时钟钩子），验证冒烟用例 `Stub_EventHandler_PostTask_DelayFires` 全绿
- [ ] 2.3 实现基础库同名桩（securec、c_utils（含 `sptr`→`std::shared_ptr` 兼容别名）、log、eventhandler、parameter、cJSON、libphonenumber）与 CallConnectAbility/CallDialog UI 桩，验证 `sanity_test`/`liteos_stub_test` 全绿
- [ ] 2.4 must-pass 门禁仍为 PASS

## 3. 移除整目录能力（antifraud / bluetooth / earthquake / voice-assistant / display / distributed / interoperable / satellite / video / js-ets-cj）

- [ ] 3.1 删除 `services/{antifraud,bluetooth,call_earthquake_alarm,call_voice_assistant,display,distributed_call,interoperable_call,satellite_call,video}/`、`sa_profile/`、`frameworks/{js,ets,cj}/`、`interfaces/kits/`，同步删除 `callmanager.gni` 中对应 sources/include_dirs 条目，验证 `ninja -C out` 编译通过
- [ ] 3.2 同步测试工程：`test/tests/BUILD.gn` 的 `mustpass_tests` 移除 `tel_call_voice_assistant_test`、`distributed_communication_test`、`tel_call_earthquake_alarm_test` 三项；删除 mini 内对应 `test/unittest/` 目录；`test/build/ohos.gni` 宏注入改为手表宏集（`ABILITY_CELLULAR_SUPPORT`/`ABILITY_SMS_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`，去掉 `ABILITY_BLUETOOTH_SUPPORT`），验证门禁 5 套件可编译
- [ ] 3.3 must-pass 门禁仍为 PASS（5 套件）

## 4. 保留目录内的单文件删除（design D2 清单）

- [ ] 4.1 删除 `services/call/src/` 中会议与类型收敛相关文件（`conference_base.cpp`、`cs_conference.cpp`、`ims_conference.cpp`、`ott_conference.cpp`、`video_call_state.cpp`、`bluetooth_call.cpp`、`bluetooth_call_state.cpp`、`satellite_call.cpp`、`ott_call.cpp`、`ott_call_connection.cpp`、`voip_call.cpp`、`call_wired_headset.cpp`、`call_superprivacy_control_manager.cpp`），同步 `callmanager.gni`，验证编译通过
- [ ] 4.2 删除 `services/call/call_state_observer/src/{proximity_sensor,status_bar,wired_headset}.cpp`、`services/telephony_interaction/src/{voip_call_connection,bluetooth_call_connection,call_status_callback_stub}.cpp`、`services/call_report/src/{app_state_observer,call_ability_callback_death_recipient,call_ability_callback_proxy}.cpp`、`services/call_manager_service/src/call_manager_service_stub.cpp`、`frameworks/native/src/` 代理与死亡通知类（design D2 表）、`services/audio/src/audio_state/{bluetooth_device_state,wired_headset_device_state,ott_call_state}.cpp`、`utils/src/{edm_call_policy,incoming_flash_reminder,motion_recognition,screen_sensor_plugin}.cpp`，同步 `callmanager.gni`，验证编译通过
- [ ] 4.3 清理保留文件中对已删类的 include 与调用点（`CreateNewCallByCallType` 仅构造 `CsCall`/`ImsCall`、会议入口删除、`CallDialog` 卫星分支删除等），并同步裁剪 mini `test/unittest/call_manager_zero_gtest/`、`call_manager_special_test/` 中引用已删类的用例，验证编译与门禁
- [ ] 4.4 新增 gtest：`CreateNewCallByCallType_OttType_ReturnsNull`、`CreateNewCallByCallType_BluetoothType_ReturnsNull`、`HandleDialRequest_OttDialType_Rejected`、`CombineConference_NotProvided_NoCrash`，全部通过
- [ ] 4.5 must-pass 门禁仍为 PASS

## 5. 特性宏退役与去守卫（design D9）

- [ ] 5.1 `callmanager.gni` 删除 12 个 `global_parts_info` 守卫块与 `target_platform == "watch"` 块，替换为固定 `call_manager_defines`（支持宏集）；`BUILD.gn` 固化 `call_manager_feature_not_support_multicall = true`、删除 `call_manager_feature_hfp_async_enable`；`bundle.json` 的 `component.features` 同步，验证 `gn gen` 无未定义 feature 报错
- [ ] 5.2 源码退役宏分支清理：`call_policy.cpp`、`ims_call.cpp` 的 `ABILITY_CONFIG_SUPPORT` 分支、`call_status_manager.cpp` 的 `AUDIO_SUPPORT` 分支、`tone.cpp` 的 `ABILITY_AUDIO_SUPPORT` 分支、`call_control_manager.cpp` 的 `HFP_ASYNC_ENABLE` 分支按未定义清理；`call_manager_service.cpp`/`call_records_manager.cpp` 的 `SUPPORT_MUTE_BY_DATABASE` 分支退役，验证编译通过
- [ ] 5.3 `cellular_call_connection.cpp` 删除 `RECONNECT_MAX_TRY_COUNT` 重连逻辑（直连无重连），新增 gtest `CellularCallConnection_StubUnavailable_ReturnsIpcConnectStubFail` 通过
- [ ] 5.4 must-pass 门禁仍为 PASS

## 6. 直连架构与类型收敛改造（design D3/D4/D10/D11）

- [ ] 6.1 `call_manager_service.cpp` 去 SystemAbility 形态（删 `MakeAndRegisterAbility`/`OnStart`/`OnAddSystemAbility`，`Init` 保留签名、幂等与失败不可用语义；音频回调注册改为 Init 时直接执行），验证 gtest `CallManagerService_RepeatedInit_Idempotent`、`CallManagerService_InitFailed_QueryReturnsLocalPtrNull` 通过
- [ ] 6.2 `call_manager_client.cpp` 改直连（去 `ConnectService`/死亡通知/重连），新增 gtest `CallManagerClient_Uninitialized_ReturnsUninit`、`CallManagerClient_Initialized_CallsServiceDirectly` 通过
- [ ] 6.3 服务面删除会议/视频/VoIP/OTT/卫星/蓝牙入口与权限校验调用（`TelephonyPermission::CheckCallerIsSystemApp` 等不调用），新增 gtest `SetMuted_NoPermissionCheck_Forwarded` 通过
- [ ] 6.4 `sptr` → `std::shared_ptr`/`std::unique_ptr`、`AppExecFwk::PacMap` → 结构体替换（design D4 落点文件），验证编译通过且既有用例不回退
- [ ] 6.5 DSDA 分支删除（`IsDsdsMode3`/`IsDsdsMode5` 恒 false 路径清理，CoreServiceClient 桩 `GetDsdsMode` 恒 0）、os_account 精简为单主帐号，新增 gtest `AnswerRequest_DsdsModeZero_AnswerDirectly`、`SelectAccountId_SingleAccount_UsesDefaultVoiceSlot` 通过
- [ ] 6.6 ffrt 调用点换桩（`call_request_handler.cpp`、`call_request_event_handler_helper.cpp`、`report_call_info_handler.cpp`、audio 各点），新增 gtest `RestoreDialingFlag_DelayTask_FiresAfterThreeSeconds`（注入时钟）、`ReportCallInfoQueue_Reports_ProcessedInOrder` 通过
- [ ] 6.7 must-pass 门禁仍为 PASS

## 7. 外部依赖 todo 占位与桩接线（design D6/D7/D8）

- [ ] 7.1 `cellular_call_connection.cpp`/`core_service_connection.cpp`/`call_setting_manager.cpp`/`telephony_cust_wrapper.cpp`/`reject_call_sms.cpp` 接客户端单例桩，新增 gtest `SetCallWaiting_InvalidSlotId_Rejected`、`CloseUnFinishedUssd_ForwardedToStub`、`RejectCallSms_SendsViaSmsClientStub` 通过
- [ ] 7.2 按 design D7 表落 todo 占位（audio/database/broadcast/powerLock/notification/spamCall/numberIdentity/rtt 标签，`rg '// todo!!!' telephony_call_manager_mini/` 清点无遗漏），新增 gtest `Ring_Play_AudioCallStubbed_NoRealPlayback`、`CallRecord_Insert_DatabaseTodo_NoWrite`、`IncomingCallNotification_Publish_NotificationTodo_NoPublish` 通过
- [ ] 7.3 `CallConnectAbility`/`CallDialog`/ability 连接类接 UI 桩，新增 gtest `CallConnectAbility_FirstCall_TriggersStubConnect`、`CallConnectAbility_ConnectDuringDisconnect_Dropped` 通过
- [ ] 7.4 must-pass 门禁仍为 PASS

## 8. 维测日志化（design D12）

- [ ] 8.1 `call_manager_hisysevent.cpp`、`call_manager_dump_helper.cpp`、`native_call_manager_hisysevent.cpp` 改日志打印（隐私字段约束不变），新增 gtest `BehaviorEvent_InvalidCombination_NotLogged`、`DumpHelper_NoSimCard_PrintsDefault`、`Logs_ContainNoPhoneNumber`（抓日志断言不含号码）通过
- [ ] 8.2 must-pass 门禁仍为 PASS

## 9. 收尾复核

- [ ] 9.1 全仓检索残留：`rg 'sptr<|ffrt::|CommonEventManager|DataShareHelper.*Insert|SystemAbility' telephony_call_manager_mini/ --glob '!stub/**'` 逐条解释或清理；`rg '// todo!!!'` 清点与 design D7 表一致
- [ ] 9.2 复核 design「需人工复核」四项（ECC `EccDialPolicy` 卫星分支删除、免权限校验、IPC 枚举保留不动值、PacMap 结构体对齐），在变更说明中标注复核结论
- [ ] 9.3 最终门禁：`cd test && bash build.sh all` 输出 `MUST-PASS GATE: PASS`（5 套件全绿），并复述 must-pass 结果
- [ ] 9.4 更新 `test/README.md` 的套件说明（5 套件 + mini 副本），验证文档与实际门禁一致

# Tasks

## 1. 基线准备与桩目录

- [ ] 1.1 整棵拷贝 `telephony_call_manager/` → `telephony_call_manager_mini/`，创建 `telephony_call_manager_mini/stub/` 空目录；验证：`diff -r` 仅新增目录、原仓零改动（git status 干净）
- [ ] 1.2 在 `stub/` 落地基础库同名桩（securec/log/eventhandler/c_utils 的 `sptr`→`std::shared_ptr` 兼容别名/系统参数 `GetParameter/SetParameter` 桩表/cJSON/libphonenumber 接口形态）；验证：编译桩自检 gtest `Stub_GetParameter_ReturnsDefaultWhenUnset` 通过（入 `liteos_stub_test` 套件）
- [ ] 1.3 在 `stub/` 落地五个跨模块客户端桩（`CellularCallClient`/`CoreServiceClient`/`CellularDataClient`/`SmsClient`/`TelephonyCustClient`，`GetInstance()` 单例 + 可配置返回值）；验证：gtest `CellularCallClientStub_DialReturnsConfiguredResult` 通过（入 `liteos_stub_test`）
- [ ] 1.4 在 `stub/` 落地 `EventHandler` 桩（FIFO 串行投递/延时任务/取消未决任务）；验证：gtest `StubbedEventHandler_ExecutesTasksInSubmitOrder` 通过（入 `liteos_stub_test`）
- [ ] 1.5 门禁回归：`test/` 下 `bash build.sh all` 输出 `MUST-PASS GATE: PASS`（此阶段仍指向未裁剪副本）

## 2. 目录级裁剪（删文件必须同步 gni）

- [ ] 2.1 删除 `services/bluetooth/`、`services/video/`、`services/satellite_call/` 三个模块组目录；同步删除 `callmanager.gni` 的 `call_manager_sources`/`call_manager_include_dirs` 对应条目；验证：gni 中 rg `services/bluetooth|services/video|services/satellite_call` 零命中
- [ ] 2.2 删除 `services/distributed_call/`（含 `transmission/`、`distributed_communication/`）与 `services/interoperable_call/`；同步 gni 条目与 `SUPPORT_MUTE_BY_DATABASE` watch 块；验证：gni 零命中
- [ ] 2.3 删除 `services/antifraud/`（含 `antiinclude/`）、`services/call_voice_assistant/`、`services/call_earthquake_alarm/`、`services/display/`；同步 gni 条目；验证：gni 零命中
- [ ] 2.4 删除不支持宏守护的观察者/工具文件：`incoming_call_notification.*`（含 `MissedCallNotification`）、`status_bar.*`、`wired_headset.*`、`incoming_call_wake_up.*`、`proximity_sensor.*`、`motion_recognition.*`、`screen_sensor_plugin.*`、`incoming_flash_reminder.*`、`interoperable_settings_handler.cpp`；同步 gni 条目；验证：gni 与 `call_manager_sources` 零命中
- [ ] 2.5 清理保留源中对已删符号的悬空引用（`CallControlManager::Init` 的 `IncomingCallWakeup`/`MissedCallNotification` 创建、`CallStateObserve` 注册表、`CallObjectManager::AddOneCallObject` 的 `CallWiredHeadSet::Init`、`StartFlashRemind`/`StartInComingCallMotionRecognition` 调用点等）；验证：编译零错误
- [ ] 2.6 删除 `frameworks/js/`、`frameworks/ets/`、`frameworks/cj/` 与 `sa_profile/`；验证：`bundle.json` 无对应 target 引用（见 3.x 同步）
- [ ] 2.7 为上行链路裁剪补 gtest：`test/unittest` 存活套件内新增 `HandleCallReportInfo_BluetoothTypeReport_IsRejectedAfterTrim`（蓝牙类型上报按未知类型拒绝）；验证：用例通过
- [ ] 2.8 门禁回归：`bash build.sh all` 输出 `MUST-PASS GATE: PASS`

## 3. 宏处置与构建重组

- [ ] 3.1 `callmanager.gni` 宏块收敛：恒定义 `ABILITY_SMS_SUPPORT`/`ABILITY_CELLULAR_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`/`OHOS_BUILD_ENABLE_TELEPHONY_CUST`（依赖指向 `stub/`）；删除 `ABILITY_BLUETOOTH_SUPPORT`/`SUPPORT_VIBRATOR`/`HICOLLIE_ENABLE`/`OHOS_SUBSCRIBE_MOTION_ENABLE`/`ABILITY_SCREENLOCKMGR_SUPPORT`/`multimedia_camera_framework`/`ABILITY_POWER_SUPPORT` 块；验证：gni 无 `global_parts_info` 引用
- [ ] 3.2 删除保留源中的不支持宏守卫代码：`HFP_ASYNC_ENABLE`（`call_control_manager.cpp` HFP 广播块）、`ABILITY_CONFIG_SUPPORT`/`ABILIT_CONFIG_SUPPORT`（carrier config 查询走默认值）、`ABILITY_AUDIO_SUPPORT`（`tone.cpp` 死分支）、`RECONNECT_MAX_TRY_COUNT`（重连块）；验证：rg 各宏名零命中
- [ ] 3.3 根 `BUILD.gn`：`declare_args()` 删 `call_manager_feature_hfp_async_enable`、保留 `call_manager_feature_not_support_multicall`；`bundle.json` `component.features`/`inner_kits`（删 `cj_telephony_call_ffi`）/`fwk_group`/`service_group` 同步；验证：`gn gen` 通过且 feature 对成
- [ ] 3.4 `test/unittest/BUILD.gn`：删 `call_earthquake_alarm_test`/`call_voice_assistant_test`/`distributed_communication_test` target，其余 target 随源调整；验证：`gn ls` 不含三个已删 target
- [ ] 3.5 为 `NOT_SUPPORT_MULTICALL` 保留补 gtest：`NotSupportMulticallFeature_HangUpFirstCallWhenLimitReached`；验证：feature 开/关两形态用例通过
- [ ] 3.6 门禁回归：`bash build.sh all` 输出 `MUST-PASS GATE: PASS`

## 4. 原语替换

- [ ] 4.1 ffrt→打桩 `EventHandler`：替换 `reportCallInfoQueue`（`report_call_info_handler.cpp`）、`reportAudioStateChangeQueue`（`audio_scene_processor.cpp`）与全部 `ffrt::submit`/`ffrt::submit_h`+delay/`ffrt::skip` 调用点；验证：rg `ffrt::` 零命中 + gtest `ReportCallsInfo_TwoUpdatesProcessedInSubmitOrder`（上行两次上报按提交顺序处理）通过
- [ ] 4.2 锁全量删除：删 `std::mutex`/`ffrt::mutex`/`ffrt::shared_mutex`/`std::shared_mutex`/递归锁（`toneStateLock_`/`clientLock_` 等）成员与 `lock()/unlock()` 调用；`TimeWaitHelper` 保留骨架（单线程立即按超时返回）；验证：rg `std::mutex|ffrt::mutex` 零命中 + 门禁编译通过
- [ ] 4.3 `sptr`→`std::shared_ptr`：全量替换（`callObjectPtrList_`/`callbackPtrList_`/`sptr<CallBase>` 等）；验证：rg `sptr<` 仅剩桩头兼容别名 + gtest `CallObjectManager_AddOneCallObject_SharedPtrLifecycle` 通过
- [ ] 4.4 `PacMap`/`WantParams`→结构体：`common_type.h` 新增 extras 结构体（`accountId`/`callType`/`videoState`/`dialScene`/`extraParams`/`bundleName` 等）与 `isNeedMuteRing` 标志字段，改造 `CallControlManager` 各入口与 `call_base.cpp`；验证：rg `PacMap` 零命中（桩头除外）+ gtest `DialCall_ExtrasStructCarriesAccountIdToStub` 通过
- [ ] 4.5 门禁回归：`bash build.sh all` 输出 `MUST-PASS GATE: PASS`

## 5. 直调架构改造

- [ ] 5.1 `CallManagerService` 去 `SystemAbility` 继承/`DECLARE_SYSTEM_ABILITY`/`MakeAndRegisterAbility`/`Publish`/`OnStart`，保留 `DelayedSingleton`+`Init()` 懒初始化；删除 `CallManagerServiceStub` 与 `Init*Request` 建表、`sa_profile` 引用；验证：rg `SystemAbility` 于 mini 业务源零命中 + gtest `CallManagerService_LazyInitOnFirstGetInstance` 通过
- [ ] 5.2 `CallManagerClient` 直调改造：删除 `CallManagerProxy`/`CallManagerServiceProxy`/死亡收件人/重连链路，`Init()` 幂等直连服务单例，未初始化返回 `TELEPHONY_ERR_UNINIT`；验证：gtest `CallManagerClient_UninitReturnsTelephonyErrUninit` 与 `CallManagerClient_DialDirectlyInvokesService` 通过
- [ ] 5.3 权限校验调用点全删（`TelephonyPermission::CheckCallerIsSystemApp`/`CheckPermission`）；IPC 码表头保留不动；验证：rg 权限校验零命中 + gtest `DialCall_NoPermissionCheckCallerIdentityIndependent` 通过
- [ ] 5.4 回调链直调化：`CallAbilityReportProxy` 直调 `ICallAbilityCallback`（`std::shared_ptr` 注册表），删 `CallAbilityCallbackProxy`/`CallStatusCallbackProxy` 打包层与死亡通知；验证：gtest `RegisterCallBack_DuplicateRegisterRejectedByRegisterStatus` 与 `UnRegisterCallBack_RemovesOnlyMatchingBundle` 通过
- [ ] 5.5 门禁回归：`bash build.sh all` 输出 `MUST-PASS GATE: PASS`

## 6. 外部依赖处置

- [ ] 6.1 跨模块交互改客户端桩：`CellularCallConnection`/`CoreServiceConnection`/`CallSettingManager`/`CallManagerService::DialCall`（语音信箱）等改 `CellularCallClient::GetInstance()`/`CoreServiceClient::GetInstance()` 形态，删 samgr/iface_cast/SA 订阅/重连；验证：gtest `DialCall_ForwardsToCellularCallClientStub`、`FDN_EnabledDialRejectedWithDueToFdn`（桩配置 FDN 名单）通过
- [ ] 6.2 功耗锁/亮屏/贴耳：`AcquireIncomingLock`/`ReleaseIncomingLock` 调用点保留为空操作占位（`// todo!!! [powerLock]`）；验证：gtest `IncomingHandle_RunsWithoutIncomingLockNoop` 通过
- [ ] 6.3 DataShare 调用点 todo 占位：`CallDataBaseHelper`/`SettingsDataShareHelper`/`NumberIdentityDataBaseHelper`/通话记录写库/黄页归属地查询；验证：gtest `QueryCallerInfo_ReturnsDefaultWhenDatabaseTodo`（联系人默认值）通过
- [ ] 6.4 广播调用点 todo 占位：七组订阅与全部 `PublishCommonEvent`（`COMMON_EVENT_SPECIAL_CODE` 等）；验证：gtest `InputDialerSpecialCode_MatchesWithoutPublishingRealBroadcast` 通过
- [ ] 6.5 通知/骚扰/号码识别/RTT 文件节点调用点 todo 占位：未接提醒、`SpamCallAdapter` 扩展连接（默认不拦截）、`NumberIdentityServiceHelper` 导入请求、`StartRtt/StopRtt` 文件节点；验证：gtest `DetectSpamCall_TimesOutToNotBlockedByDefault`、`StartRtt_KeepsInterfaceWithFileNodeTodo` 通过
- [ ] 6.6 `CallConnectAbility`/`CallDialog` 界面与弹窗经桩：`AbilityManagerClient::ConnectAbility` 与 sceneboard 对话框桩空执行；验证：gtest `ConnectAbility_StubNoRealUiLifecycleCompletes` 与 `DialogConnectExtension_StubReturnsSuccess` 通过
- [ ] 6.7 维测改日志：`CallManagerHisysevent` 各 `Write*Event`/`FinishAsyncTrace` 改日志（隐私红线：号码不进日志）；验证：gtest `WriteHangUpFaultEvent_LogsConvertedErrorCode` 通过
- [ ] 6.8 `TelephonyCustWrapper` 改 `TelephonyCustClient::GetInstance()` 桩（删 dlopen）；验证：gtest `IsHideViolenceOrEmcNumbers_CustClientStubDefaultFalse` 通过
- [ ] 6.9 门禁回归：`bash build.sh all` 输出 `MUST-PASS GATE: PASS`

## 7. 保留能力专项

- [ ] 7.1 ECC 主干：`CheckNumberIsEmergency` 经桩、`DialPolicy` 豁免、`HasNormalCall` 查卡经 `CoreServiceClient` 桩、`SetIsEccContact(true)`、ECC 强制不静音；验证：gtest `DialEmergencyNumber_BypassesMulticallLimitButChecksSimState` 与 `SetMute_ForcedOffDuringEmergencyCall` 通过
- [ ] 7.2 DSDS/单卡/单主帐号：`CoreServiceClient` 桩 `GetDsdsMode()` 恒 0、`DisconnectedHandle` 仅同 slot 默认恢复、OsAccount 精简；验证：gtest `GetDsdsMode_AlwaysReturnsZeroOnLiteos` 与 `DisconnectedHandle_UnHoldsSameSlotHeldCallOnly` 通过
- [ ] 7.3 VoIP 保留：`VoIPCall`/`voipCallObjectList_`/冲突处理保留，`VoipCallConnection` 桩化（`ClearVoipCall` 清场逻辑保留）；验证：gtest `DialCallBase_RejectsIncomingVoipConflictBeforeCellularDial` 与 `ClearVoipCall_ReportDisconnectedAndDeletesObjects` 通过
- [ ] 7.4 音频收敛：设备路由仅听筒/扬声器、CRS/振动/外设分支删除、音频 API 调用点占位且 `toneState_` 照常推进；验证：gtest `InitAudioDevice_ChoosesBetweenEarpieceAndSpeakerOnly` 与 `PlayCallEndedTone_ToneStateAdvancesWithAudioTodo` 通过
- [ ] 7.5 OOBE/免打扰/一号双终端：OOBE 判定改桩参数表、免打扰查询占位默认不拒接、ESIM 联动移除；验证：gtest `ShouldRejectIncomingCall_OobeUnprovisionedFromStubParamTable` 通过
- [ ] 7.6 `SendCallUiEvent` 路由收敛与 `HandleDisplaySpecifiedCallPage`/celia 事件保留；验证：gtest `SendCallUiEvent_RoutesDisplaySpecifiedCallPageViaStub` 通过
- [ ] 7.7 序列化对拍保留：`WriteCallAttributeInfo`/`ReadCallAttributeInfo` 字段序对称；验证：gtest `WriteAndReadCallAttributeInfo_VoipFieldsRoundTrip` 通过
- [ ] 7.8 门禁回归：`bash build.sh all` 输出 `MUST-PASS GATE: PASS`

## 8. test/ 门禁联动

- [ ] 8.1 `test/base/telephony/call_manager` 软链切向 `telephony_call_manager_mini/`；验证：`gn ls //base/telephony/call_manager:*` 解析到 mini 的 target
- [ ] 8.2 `tests/BUILD.gn` `mustpass_tests` 移除 `tel_call_voice_assistant_test`/`distributed_communication_test`/`tel_call_earthquake_alarm_test`，保留 5 套件；`run_tests.sh` 套件清单同步；验证：门禁输出仅运行 5 套件
- [ ] 8.3 `build/ohos.gni` 注入宏改手表宏集（删 `ABILITY_BLUETOOTH_SUPPORT=0x1`，加 `ABILITY_SMS_SUPPORT` 等）；验证：编译产物 defines 含手表宏集、不含蓝牙宏
- [ ] 8.4 门禁全绿：`bash build.sh all` 输出 `MUST-PASS GATE: PASS`（5 套件全 rc=0、0 FAILED）

## 9. 最终验收

- [ ] 9.1 对照 delta specs 逐能力核对裁剪结果（REMOVED 项 rg 零命中、MODIFIED 项行为与场景一致、`liteos-runtime` 场景全部可落 gtest）；验证：核对清单全部勾选
- [ ] 9.2 全量检查：mini 内 rg `dlopen|samgr|SystemAbility|ffrt::|sptr<|PublishCommonEvent`（桩与 todo 注释行除外）零命中；`openspec validate --all --strict` 通过
- [ ] 9.3 终验：`bash build.sh all` 输出 `MUST-PASS GATE: PASS` 且各新增 gtest 用例全绿

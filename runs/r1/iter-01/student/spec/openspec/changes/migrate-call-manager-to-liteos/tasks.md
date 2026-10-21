# Tasks

## 0. 门禁与前置

- [ ] 0.1 在本机 `test/` 下执行 `bash build.sh all`，确认未裁剪副本门禁为 PASS（`MUST-PASS GATE: PASS`，8 套件 121/121，对应 tag `baseline-unmodified`）；记录日志路径作为本变更所有任务组的回滚对照
- [ ] 0.2 从 `telephony_call_manager/` 整棵拷贝出 `telephony_call_manager_mini/`（目录、文件命名一致，不拷贝 figures/README 等 non-build 资产），暂不裁剪；验证 `git status --porcelain` 中 `telephony_call_manager/` 无改动、`test/base/telephony/call_manager` 软链仍指向 `telephony_call_manager/` 时门禁 PASS

> 本变更所有任务组的完成条件之一：本组任务后 `bash build.sh all` 的 must-pass 门禁仍为 PASS（裁剪过程中按能力组逐步从 8 套件收敛为 5 套件，见组 9）。

## 1. 桩层与基础替换（liteos-stub-layer delta / design D5/D6/D8）

- [ ] 1.1 创建 `telephony_call_manager_mini/stub/` 目录；实现客户端单例桩 `stub/cellular_call_client.*`、`stub/core_service_client.*`、`stub/cellular_data_client.*`、`stub/sms_client.*`、`stub/telephony_cust_client.*`、`stub/voip_call_client.*`、`stub/state_registry_client.*`（`GetInstance()` 单例、默认返回“服务未连接”语义失败码、测试可注入返回值）；验证：gtest `StubClientDefaultFailsLikeServiceUnavailable`（未注入时拨号请求走基线失败分支）与 `StubClientInjectedSuccessDrivesCarrierDialProcess`（注入成功后 `CallRequestProcess::CarrierDialProcess` 收到请求）通过
- [ ] 1.2 实现同名桩：`stub/eventhandler_stub.*`（PostTask/队列/延迟原语，当前线程同步串行执行）、`stub/hisysevent_stub.*`（`HiSysEventWrite`→日志一行）、`stub/parameter_stub.*`、`stub/cjson_stub.*`、`stub/phonenumber_stub.*`、`stub/securec_stub.*`、`stub/c_utils_stub.*`、`stub/log_stub.*`（hilog 同名）；验证：gtest `HisyseventStubWritesLogWithoutPhoneNumber`（事件名入日志、无号码明文）与 `StubEventHandlerRunsInlineInOrder` 两个用例通过
- [ ] 1.3 全仓把桩加入构建并标注 todo：`callmanager.gni` 的 `call_manager_sources` 追加 stub 源（见组 7 宏块同步），include_dirs 追加 stub 头目录；验证：gn 生成与编译无未定义符号（**需人工复核**：与基线错误码逐点对齐，见 liteos-stub-layer delta“桩默认拒绝”场景）
- [ ] 1.4 全仓类型替换：`sptr<T>`→`std::shared_ptr<T>`（`wptr`→`std::weak_ptr`）、`DelayedSingleton` 保留模板形态改静态单例实现；删除全部锁（std::mutex/ffrt::mutex/shared_mutex 用具与成员）；ffrt 调用点改 `stub/eventhandler_stub` 原语；验证：gtest `ReportCallInfoQueueStillSerializesUplink`（上行单队列串行语义保持）通过且门禁 PASS

## 2. 整删能力：源文件删除与 gni 同步（design D7 删除文件表）

- [ ] 2.1 删除以下目录全部源文件并同步 `callmanager.gni`（sources 与 include_dirs 去除对应条目）：`services/antifraud/`、`services/bluetooth/`、`services/call_earthquake_alarm/`、`services/call_voice_assistant/`、`services/display/`、`services/distributed_call/`（含 distributed_communication/ 与 transmission/ 子目录）、`services/interoperable_call/`、`services/satellite_call/`、`services/video/`；验证：gn 编译通过（被删符号无残留引用，若有引用逐个补删调用点）
- [ ] 2.2 删除 `services/call/src/` 下：`bluetooth_call.cpp/.h`、`bluetooth_call_state.cpp/.h`、`call_superprivacy_control_manager.cpp/.h`、`call_wired_headset.cpp/.h`、`conference_base.cpp/.h`、`cs_conference.cpp/.h`、`ims_conference.cpp/.h`、`ott_call.cpp/.h`、`ott_call_connection.cpp/.h`、`ott_conference.cpp/.h`、`satellite_call.cpp/.h`、`video_call_state.cpp/.h`、`net_call_base.cpp/.h`，并同步 `callmanager.gni`；验证：编译通过且 gtest `ObjectTableOnlyHoldsCSImsVoipTypes`（对象表仅余 CS/IMS/VoIP 类型）通过
- [ ] 2.3 删除 `services/call/call_state_observer/src/` 下 `proximity_sensor.cpp/.h`、`status_bar.cpp/.h`、`wired_headset.cpp/.h`，并同步 `callmanager.gni`；删除 `services/telephony_interaction/src/bluetooth_call_connection.cpp/.h`、`services/call_manager_service/src/call_manager_service_stub.cpp/.h`（HICOLLIE_ENABLE 场点随文件消亡），并同步 `callmanager.gni`；验证：编译通过
- [ ] 2.4 删除 `utils/src/` 下 `edm_call_policy.cpp/.h`、`incoming_flash_reminder.cpp/.h`、`motion_recognition.cpp/.h`、`screen_sensor_plugin.cpp/.h`，并同步 `callmanager.gni` + 删除 `OHOS_SUBSCRIBE_MOTION_ENABLE` gni 块；验证：编译通过且 rg `EdmCallPolicy|IncomingFlashReminder|MotionRecogntion|ScreenSensorPlugin` 于 mini 仅剩历史注释无活调用
- [ ] 2.5 删除 `frameworks/native/` 下 `bluetooth_call_client.cpp/.h`、`bluetooth_call_proxy.cpp/.h`、`i_bluetooth_call.h`、`nearlink_call_client.cpp`、`super_privacy_manager_client.cpp/.h`、`call_manager_proxy.cpp/.h`、`call_manager_service_proxy.cpp/.h`、`call_status_callback_proxy.cpp/.h`、`cellular_call_proxy.cpp/.h`、`cellular_call_callback_death_recipient.cpp/.h`、`call_manager_death_recipient.cpp/.h`、`call_ability_callback_proxy.cpp/.h`、`call_ability_callback_death_recipient.cpp/.h`，并同步 `frameworks/native/BUILD.gn` 与 `callmanager.gni`；`frameworks/js`、`frameworks/ets`、`frameworks/cj`、`interfaces/kits` 不迁移整目录；验证：编译通过
- [ ] 2.6 逐能力在 delta 标注的调用点做悬空调用清扫（防诈入口 `SetupAntiFraudService`/`TriggerAntiFraudDetect`/`HandleCeliaCall`、蓝牙/分布式观察者、会议/视频控制转发、超级隐私弹窗入口 `CallDialog` 三入口）补删；验证：rg 悬空符号仅零命中 + 门禁 PASS
- [ ] 2.7 为“整删后不可达”补充负向 gtest：`NoConferenceControlApiReachable`、`NoBluetoothDialPathReachable`、`NoSetuperPrivacyApiReachable`（确认控制面拒绝/无注册路径），全部通过后本组收尾：must-pass 门禁 PASS（套件集合暂不变，见组 9）

## 3. 调度与门面改造（call-manager-service / native-client-api / call-report delta；design D2/D3）

- [ ] 3.1 `CallManagerService` 去 SystemAbility/safwk/samgr 形态：删 `OnStart`/`OnAddSystemAbility` SA 装饰与 `RegisterSystemAbility` 类调用，改进程内单例 + 本地初始化（保留蜂窝/VoIP 回调注册语义，经适配器桩）；验证：gtest `CallManagerServiceInitRegistersCellularCallbackViaStubClient`（桩收到注册调用）通过
- [ ] 3.2 移除接口权限校验（**需人工复核**）；验证：gtest 组 `PermissionCheckRemoved`：`DialCallNoPermissionCheckStillProceeds`（无任何权限框架时拨号转发仍到达 `CallControlManager`）、`UnRegisterObserverWithoutPermissionSucceeds` 通过
- [ ] 3.3 `CallManagerClient` 直调改造（`call_manager_client.cpp` 的 `Init` 直取 `CallManagerService` 单例；`HasVoiceCapability` 经参数桩）；验证：gtest `CallManagerClientBindsLocalServiceWithoutSamgr`、`HasVoiceCapabilityReadsParameterStub` 通过
- [ ] 3.4 回调直调化：`CallAbilityReportProxy`/`CallAbilityCallbackProxy` 改持对象直调（两路上报 `UpdateCallState` 与 `UpdateCallStateForSlotId` 并存保留），`CallAbilityCallbackStub` 收敛为薄入口，删除 death recipient 路径；验证：gtest 两路并存用例 `BothGlobalAndSlotReportProxiesSurviveDirectCall`、`UnregisterObserverRemovesCallback`（IPC 枚举值不动——**需人工复核**：对照 `call_manager_service_ipc_interface_code.h` 基线值零改动）通过
- [ ] 3.5 `call_manager_service.cpp` Celia/新通话族删除（`dealCeliaCallEvent`/`HandleCeliaAutoAnswerCall`/`IS_CELIA_CALL` 链与 `HandleVideoRingPlayFail` 视频彩振面），`IsNewCallAllowed` 保留；验证：gtest `IsNewCallAllowedStillEnforcedWhileDialing` 通过
- [ ] 3.6 拨号链保留面：`supportSpecialCode_` 集合保留、广播发布点标 `// todo!!! [broadcast] ref to call_manager_service.cpp InputDialerSpecialCode`；语音信箱计数清零出口改调 `stub/core_service_client`（`SetVoiceMailCount`），标 todo；验证：gtest `SpecialCodeMatchKeptButPublishIsTodoStub`、`VoiceMailCountResetViaCoreServiceStub` 通过；本组收尾：must-pass 门禁 PASS

## 4. 交互层改造（telephony-interaction / call-setting / audio delta；design D4/D6）

- [ ] 4.1 `CellularCallConnection`/`CoreServiceConnection`/`TelephonyCustWrapper` 适配器改造：内部改调 `XxxClient::GetInstance()` 桩（不再 dlopen）；删除 `RECONNECT_MAX_TRY_COUNT` 宏块；验证：gtest `ReConnectServiceFailureMapsToBaselineError`（桩默认失败→基线错误码）通过（**需人工复核**：错误码/结构体对齐）
- [ ] 4.2 `VoipCallConnection` 改 `stub/voip_call_client`（保留注册/Answer/Reject/HangUp/SendCallUiEvent 语义与冲突链），标 `// todo!!! [callUi] ref to voip_call_connection.cpp SendCallUiEvent`；验证：gtest `VoipConflictStillExchangesStateWithCellular`（NOT_SUPPORT_MULTICALL 抢占链保持）通过
- [ ] 4.3 `ReportCallInfoHandler` 上行队列改桩 EventHandler；OOBE 蓝牙过滤分支删；`CallStatusCallback` 直调化与 Ss/Ussd/Mmi/Rtt/Dtmf 结果回调语义保留，媒体面回调族随视频/会议删；1s/3s 延迟改桩；验证：gtest `UplinkStillSingleQueued`、`WaitingToneTimerUsesStubTimer` 通过
- [ ] 4.4 音频出口全量 todo：AudioProxy/Ring/Sound/Tone/AudioPlayer 对 audio_framework 调用点标 `// todo!!! [audio] ref to <file> <func>`，逻辑保留、桩默认失败走基线失败分支；验证：gtest `MuteKeptWhileAudioServiceUnavailable`（桩失败时静音状态照抄基线置位）通过
- [ ] 4.5 音频路由收敛为听筒/扬声器：删彩振（dealCrsScene/crsType==CRS_TYPE 族）、振动（SUPPORT_VIBRATOR）调点、近场/蓝牙路由，将为 REMOVED 的分支调用点删除；验证：gtest `NoRingtoneWhenCrsTypeVideo`、设备路由 `SpeakerEarpieceSwitchStillTracked` 通过；本组收尾：must-pass 门禁 PASS

## 5. 状态与观察者层（call-status-management / call-state-observer / spam / number-identity delta）

- [ ] 5.1 删除 DSDA 非零、防诈、Celia/蓝牙/分布式/运动识别分支及其调用点（含 `HoldOrDisconnectedCall`→`HandleCallWaitingNum*` 矩阵调用链与 `IsDialCallForDsda` 置位），slotId 参数面保留；验证：gtest `SingleCardDialNeverEntersDsdaMatrix`、`slotIdPreservedInAllRequests` 通过
- [ ] 5.2 来话判定链保留面：OOBE/免打扰/焦点模式/响一声判定链照抄，外部出口分别标 `[database]`/`[notification]`；spam 检测链保留、`ConnectSpamCallAbility` 等标 `[spamCall]`（**需人工复核**：拦截判定树与基线分支逐条对照）；验证：gtest 组 `IncomingDecisionTreeKept`：`EccAllowedWhileInCall`、`OobeNotProvisionedRejects`、`DndSilentNoLiftInCallStack`、`DoNotDisturbRetryBecomesRingOnce` 通过；**紧急呼叫（ECC）豁免链必须整组具名 gtest 全过才算本子任务完成**
- [ ] 5.3 通知/记录链 todo 化：`IncomingCallNotification`/`MissedCallNotification` 标 `[notification]`；`CallRecordsHandler`/`CallDataBaseHelper` DataShare 调点标 `[database]`；`IncomingCallWakeup` RunningLock 调点标 `[powerLock]`；`reject_call_sms` 出口改 `SmsClient::GetInstance()` 桩；验证：gtest `RecordFlowCompleteThoughDatabaseTodo`（入库失败时未读置位照抄）、`RejectSmsSentViaStubClient` 通过
- [ ] 5.4 `CallConnectAbility`/`CallDialog`/`CallAbilityConnection` UI 拉起链打桩（标 `[callUi]`），失连降级行为照抄；HSDR 广播订阅保留、订阅调用点标 `[broadcast]`，防诈侧消费删；`SpamCallConnection` 残余文件按 design OQ6 保留可编译最小形（**需人工复核**）；验证：gtest `IncomingCallStillHandledWhenUiStubFails`、`HsdrEventStillDispatchedToNumberIdentity` 通过；本组收尾：must-pass 门禁 PASS

## 6. utils 与维测（call-utils / hisysevent-diagnostics delta）

- [ ] 6.1 `CallNumberUtils` 主链保留：libphonenumber 桩、parameter 桩、`SelectAccountId` 改 `stub/cellular_data_client`；`SettingsDataShareHelper` 查询/订阅调点标 `[database]`（含 `wear_status` 键）；`CallManagerUtils::IsBundleInstalled` ability 查询出口标 `[callUi]`；验证：gtest `EmergencyNumberStillDetectedWithStubLibphonenumber`、`WearStatusGateReadsSettingViaStub` 通过
- [ ] 6.2 `CallManagerHisysevent` 全事件面改 `stub/hisysevent_stub`（签名不变、日志输出），`CallManagerDumpHelper` Dump 走日志；号明文红线 gtest `NoPhoneNumberInAnyEventLog`（遍历事件写入断言无号码）通过；本组收尾：must-pass 门禁 PASS
- [ ] 6.3 todo 标签全量自检：`rg -n "todo!!!\\[(audio|database|broadcast|powerLock|callUi|notification|spamCall|numberIdentity|rtt)\\] ref to " telephony_call_manager_mini/` 按能力 delta 清单逐条核对调用点无遗漏、语法统一；输出清单入 change 备注

## 7. 构建面与配置（build-config delta；design D7/D10）

- [ ] 7.1 `callmanager.gni`：宏部件块删除 6 个（communication_bluetooth、sensors_miscdevice、hiviewdfx_hicollie、msdp_motion、theme_screenlock_mgr、multimedia_camera_framework）、保留 6 个（telephony_sms_mms、telephony_cellular_call、powermgr_power_manager、telephony_cellular_data、telephony_telephony_enhanced、telephony_telephony_cust）；`target_platform=="watch"` 特设块（SUPPORT_MUTE_BY_DATABASE 与 interoperable_settings_handler.cpp）删除；external_deps 收敛为桩可满足集合；验证：编译通过
- [ ] 7.2 根 `BUILD.gn`：删 `call_manager_feature_hfp_async_enable` declare_args 与 `HFP_ASYNC_ENABLE` define 注入，删 `HfpBroadcastSubscriber` 守卫块；`call_manager_feature_not_support_multicall` 保留原语义；验证：gn 生成通过，feature 开关两个状态编译均通过（保留宏）为零差异输出
- [ ] 7.3 `bundle.json`：`component.features` 删 `call_manager_feature_hfp_async_enable`、留 `call_manager_feature_not_support_multicall`；syscap/inner_kits 面收敛随实际；`sa_profile/` 目录不迁移（连同两份 json 删除）
- [ ] 7.4 测试 target 裁剪：unittest/fuzztest 中被删模块 target（earthquake_alarm、voice_assistant、distributed_communication、conference/bluetooth/satellite/antifraud/spam connection 系 fuzz）删除，0/5/2 系列 target 保留并随裁剪修正用例内被删符号引用；每删 target 附“文件在 mini test 目录原位维护”说明；验证：`gn gen` + 被测测试 target 编译零错误
- [ ] 7.5 强制宏集切换：`test/build/ohos.gni` 系兼容层（或其 force_includes 等注入点）把 `ABILITY_BLUETOOTH_SUPPORT=0x1` 移出注入集（含 0 值注入或不注入、与 mini 无该宏场点一致），保留 `ABILITY_CELLULAR_SUPPORT=0x1`；验证：gn 生成的 ninja 命令行 `rg ABILITY_BLUETOOTH_SUPPORT` 零命中
- [ ] 7.6 门禁套件调整：`test/tests/BUILD.gn` 的 `mustpass_tests` 移除 `tel_call_voice_assistant_test`、`distributed_communication_test`、`tel_call_earthquake_alarm_test`，must-pass 收敛为 5 套件（sanity_test、liteos_stub_test、zero2、zero5、special2）；验证：must-pass 输出 PASS

## 8. 路径切换与端到端验收（pc-test-harness delta；design D11）

- [ ] 8.1 `test/base/telephony/call_manager` 软链改指 `telephony_call_manager_mini/`；验证：gn 解析编译生效，mini 的桩目录纳入被测编译（见 build-config delta ADDED 场景）
- [ ] 8.2 被“整拷前置门禁”（任务 0.2）印证过的三个套件（voice assistant、earthquake、distributed_communication）删除后再次核验 must-pass 门禁 5 套 PASS
- [ ] 8.3 端到端验收：对照 openspec delta 清单逐能力跑一遍对应 gtest 清单（组 1~7 全部用例名称），并跑 `openspec validate --all --strict` PASS，作为整个 change 的完收门禁（`bash build.sh all` + `MUST-PASS GATE: PASS`）

## 9. 复核与收尾

- [ ] 9.1 ECC 判定链复核：拨号豁免、拒接抵消、紧急呼救强制放行、isChangeDialNumberToTwEmc_ 改写各配一条自解释 gtest（拨号链与来话豁免两侧），全过（**需人工复核**：判定树与基线逐分支对照签字）
- [ ] 9.2 IPC 枚举/跨部件结构体复核：对照基线 `interfaces/innerkits/` 各 `*_ipc_interface_code.h` 枚举值零改动（**需人工复核**），跨部件数据结构（CallAttributeInfo/CellularCallInfo/PacMap→结构体替换）与基线字段对照一致（**需人工复核**）
- [ ] 9.3 design Open Questions 六项逐条回执：实施默认值均已落地（照抄不修缺陷、CONFIG_FACTORY_VERSION 无动作、versionscript 不迁移、EventHandler 栈不新增线程、spam 三文件最小形），评审如改动任何一个，同步修订对应 delta 与本清单
- [ ] 9.4 最终 grep 清扫：对 design D7 删除文件表全部符号跑 `rg` 检查 mini 无活引用（仅历史注释/REMOVED 记录），`git status --porcelain` 确认 telephony_call_manager/ 与 test/ 框架文件除 changes 外无改动；输出验收摘要（含 8.3 的门禁结果）
# Deterministic metrics: reference vs student

Computed by script, not by a model. Capability ids are compared literally; a
student may use different ids for the same module group, so read them as hints.

| metric | reference | student |
|---|---|---|
| baseline capabilities | 24 | 24 |
| baseline requirements | 127 | 145 |
| baseline scenarios | 143 | 374 |
| change exists | True | True |
| proposal.md lines | 77 | 97 |
| design.md lines | 241 | 186 |
| tasks.md lines | 82 | 74 |
| design decisions (headings) | 2 | 2 |
| tasks (checkboxes) | 53 | 36 |
| delta ADDED requirements | 7 | 0 |
| delta MODIFIED requirements | 63 | 79 |
| delta REMOVED requirements | 59 | 61 |
| delta RENAMED requirements | 0 | 0 |
| reference grounding (backticked names found in HMOS) | 1568/1653 | 1925/2018 |
| openspec validate --all --strict | True | True |
| only openspec/ written | True | True |

## Baseline capability ids

- shared: antifraud-call, bluetooth-call, call-earthquake-alarm, call-manager-service, call-object-model, call-report, call-setting, call-state-observer, call-voice-assistant, distributed-call, interoperable-call, satellite-call, spam-call, telephony-interaction, video-call
- only reference: audio-control-manager, build-and-feature-flags, call-control-manager, call-manager-utils, call-status-manager, client-frameworks, fold-display, hisysevent-observability, number-identity
- only student: audio-management, call-control, call-status-management, call-utils, client-framework, display-control, hisysevent-dfx, js-ets-cj-binding, number-identity-proxy

## Feature macros mentioned in the change

- shared: ABILITY_AUDIO_SUPPORT, ABILITY_BLUETOOTH_SUPPORT, ABILITY_CAMERA_FRAMEWORK_SUPPORT, ABILITY_CAMERA_SUPPORT, ABILITY_CELLULAR_SUPPORT, ABILITY_CONFIG_SUPPORT, ABILITY_DISPLAY_SUPPORT, ABILITY_MEDIA_SUPPORT, ABILITY_NOTIFICATION_SUPPORT, ABILITY_POWER_SUPPORT, ABILITY_SCREENLOCKMGR_SUPPORT, ABILITY_SMS_SUPPORT, ABILITY_STATUS_BAR_CONTROL_SUPPORT, CALL_MANAGER_AUTO_START_OPTIMIZE, CALL_MANAGER_CALL_TRANSFER, CALL_MANAGER_SOS_NO_RINGBACK_TONE, CALL_MANAGER_THERMAL_PROTECTION, CALL_MANAGER_WATCH_CALL_BLOCKING, CELLULAR_DATA_SUPPORT, CONFIG_FACTORY_VERSION, CRS_TYPE, HFP_ASYNC_ENABLE, HICOLLIE_ENABLE, NOT_SUPPORT_MULTICALL, OHOS_BUILD_ENABLE_TELEPHONY_CUST, OHOS_SUBSCRIBE_MOTION_ENABLE, OHOS_SUBSCRIBE_USER_STATUS_ENABLE, RECONNECT_MAX_TRY_COUNT, SUPPORT_DSOFTBUS, SUPPORT_HEARING_AID, SUPPORT_MUTE_BY_DATABASE, SUPPORT_RTT_CALL, SUPPORT_VIBRATOR, TELEPHONY_CUST_SUPPORT
- only reference: ABILIT_CONFIG_SUPPORT
- only student: AUDIO_SUPPORT, MAKE_CALL_WITH_TOKEN

## Student names that were not found in the HMOS tree

These are either new code introduced by the student's design (stubs, structs,
todo labels) or hallucinated references. Check before penalizing.

- `/rms/v1/antiFraud/upload-model-result`
- `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true&key=`
- `OnXxx`
- `call_ability_report_proxy.cpp/.h`
- `call_state_report_proxy.cpp/.h`
- `call_ability_callback_proxy.cpp/.h`
- `call_ability_callback_death_recipient.cpp/.h`
- `app_state_observer.cpp/.h`
- `call_data_base_helper.cpp/.h`
- `call_records_handler.cpp/.h`
- `call_records_manager.cpp/.h`
- `incoming_call_notification.cpp/.h`
- `missed_call_notification.cpp/.h`
- `incoming_call_wake_up.cpp/.h`
- `proximity_sensor.cpp/.h`
- `reject_call_sms.cpp/.h`
- `status_bar.cpp/.h`
- `wired_headset.cpp/.h`
- `datashare:///com.ohos.contactsdataability/contacts/contact_blocklist`
- `call_status_manager.cpp/.h`
- `call_status_policy.cpp/.h`
- `call_state_listener.cpp/.h`
- `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true`
- `call_voice_assistant_manager.cpp/.h`
- `fold_status_manager.cpp/.h`
- `transport/socket.h`
- `call_manager_hisysevent.cpp/.h`
- `call_manager_dump_helper.cpp/.h`
- `makeCallFunc`
- `startAbility`
- `CallAttributeOptions`
- `datashare:///numberlocationability`
- `datashare:///numbermarkability/number_mark_info`
- `input/camera_manager.h`
- `telephony_call_manager_mini/`
- `specs/`
- `stub/`
- `XxxClient::GetInstance`
- `telephony_call_manager_mini/stub/`
- `ICellularCall`
- `ICoreService`
- `AlertDialog`
- `#ifdef/#else`
- `CsCall`
- `ImsCall`
- `telephony_call_manager_mini/callmanager.gni`
- `mustpass_tests`
- `${_cm}/call_voice_assistant_test`
- `${_cm}/distributed_communication_test`
- `${_cm}/call_earthquake_alarm_test`
- `telephony_call_manager_mini/test/unittest/`
- `ISmsServiceInterface`
- `build/ohos.gni`
- `build/test.gni`
- `static_library`
- `shared_library`
- `ohos_static_library`
- `_pc_blocklist`
- `_pc_force_includes`
- `dlfcn.h`
- `securec.h`
- `//stubs:ext_ohos`
- `tests/BUILD.gn`
- `sanity_test`
- `liteos_stub_test`
- `${TMPDIR:-/tmp}/gn_<suite>.$UID.log`
- `Stub_XxxClient_GetInstance_ReturnsDefault`
- `Stub_EventHandler_PostTask_DelayFires`
- `CreateNewCallByCallType_OttType_ReturnsNull`
- `CreateNewCallByCallType_BluetoothType_ReturnsNull`
- `HandleDialRequest_OttDialType_Rejected`
- `CombineConference_NotProvided_NoCrash`
- `CellularCallConnection_StubUnavailable_ReturnsIpcConnectStubFail`
- `CallManagerService_RepeatedInit_Idempotent`
- `CallManagerService_InitFailed_QueryReturnsLocalPtrNull`
- `CallManagerClient_Uninitialized_ReturnsUninit`
- `CallManagerClient_Initialized_CallsServiceDirectly`
- `SetMuted_NoPermissionCheck_Forwarded`
- `AnswerRequest_DsdsModeZero_AnswerDirectly`
- `SelectAccountId_SingleAccount_UsesDefaultVoiceSlot`

# Deterministic metrics: reference vs student

Computed by script, not by a model. Capability ids are compared literally; a
student may use different ids for the same module group, so read them as hints.

| metric | reference | student |
|---|---|---|
| baseline capabilities | 24 | 24 |
| baseline requirements | 127 | 275 |
| baseline scenarios | 143 | 732 |
| change exists | True | True |
| proposal.md lines | 77 | 83 |
| design.md lines | 241 | 223 |
| tasks.md lines | 82 | 77 |
| design decisions (headings) | 2 | 2 |
| tasks (checkboxes) | 53 | 44 |
| delta ADDED requirements | 7 | 5 |
| delta MODIFIED requirements | 63 | 161 |
| delta REMOVED requirements | 59 | 104 |
| delta RENAMED requirements | 0 | 0 |
| reference grounding (backticked names found in HMOS) | 1568/1653 | 3405/3701 |
| openspec validate --all --strict | True | True |
| only openspec/ written | True | True |

## Baseline capability ids

- shared: antifraud-call, bluetooth-call, call-manager-service, call-report, call-state-observer, distributed-call, interoperable-call, number-identity, satellite-call, telephony-interaction
- only reference: audio-control-manager, build-and-feature-flags, call-control-manager, call-earthquake-alarm, call-manager-utils, call-object-model, call-setting, call-status-manager, call-voice-assistant, client-frameworks, fold-display, hisysevent-observability, spam-call, video-call
- only student: audio-device-management, build-config, call-control-management, call-object-management, call-setting-management, call-status-management, call-utils, display-management, earthquake-alarm-call, hisysevent-diagnostics, native-client-api, spam-call-identification, video-call-control, voice-assistant-call

## Feature macros mentioned in the change

- shared: ABILITY_AUDIO_SUPPORT, ABILITY_BLUETOOTH_SUPPORT, ABILITY_CAMERA_FRAMEWORK_SUPPORT, ABILITY_CAMERA_SUPPORT, ABILITY_CELLULAR_SUPPORT, ABILITY_CONFIG_SUPPORT, ABILITY_DISPLAY_SUPPORT, ABILITY_MEDIA_SUPPORT, ABILITY_NOTIFICATION_SUPPORT, ABILITY_POWER_SUPPORT, ABILITY_SCREENLOCKMGR_SUPPORT, ABILITY_SMS_SUPPORT, ABILITY_STATUS_BAR_CONTROL_SUPPORT, ABILIT_CONFIG_SUPPORT, CALL_MANAGER_AUTO_START_OPTIMIZE, CALL_MANAGER_CALL_TRANSFER, CALL_MANAGER_SOS_NO_RINGBACK_TONE, CALL_MANAGER_THERMAL_PROTECTION, CALL_MANAGER_WATCH_CALL_BLOCKING, CELLULAR_DATA_SUPPORT, CONFIG_FACTORY_VERSION, CRS_TYPE, HFP_ASYNC_ENABLE, HICOLLIE_ENABLE, NOT_SUPPORT_MULTICALL, OHOS_BUILD_ENABLE_TELEPHONY_CUST, OHOS_SUBSCRIBE_MOTION_ENABLE, OHOS_SUBSCRIBE_USER_STATUS_ENABLE, RECONNECT_MAX_TRY_COUNT, SUPPORT_DSOFTBUS, SUPPORT_HEARING_AID, SUPPORT_MUTE_BY_DATABASE, SUPPORT_RTT_CALL, SUPPORT_VIBRATOR, TELEPHONY_CUST_SUPPORT
- only reference: -
- only student: AUDIO_SUPPORT, MAKE_CALL_WITH_TOKEN, TELEPHONY_EXIT_STR, TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID

## Student names that were not found in the HMOS tree

These are either new code introduced by the student's design (stubs, structs,
todo labels) or hallucinated references. Check before penalizing.

- `USER_IMPROLAN_SWITCH`
- `serviceName`
- `base64.h`
- `ENABLE_DEVICE_EARPIECE/SPEAKER/WIRED_HEADSET/BLUETOOTH`
- `DEVICE_TYPE_WIRED_HEADSET/WIRED_HEADPHONES/USB_HEADSET`
- `frameworks/native:tel_call_manager_api`
- `frameworks/cj:cj_telephony_call_ffi`
- `test/unittest:unittest`
- `test/fuzztest:fuzztest`
- `tel_call_manager_zero2_gtest/zero4/zero5/zero6/zero7/zero8/zero9/zero10_gtest`
- `tel_call_manager_special1_test/special3_test`
- `HandleCallWaitingNumTwo/One/Zero`
- `AppMgr`
- `CallManagerManager::Init`
- `IsChangeDialNumberToTwEmc_`
- `EVENT_BLUETOOTH_SCO_STATE_OFF/ON`
- `OttCall::HandleCombineConferenceFailEvent`
- `观察者列表并把通话状态/事件/结果多播给全部注册方；`
- `CallControlManager::InitEvents`
- `app_state_observer.h/cpp`
- `RESTRICTION_MODE_DEACTIVATION/ACTIVATION`
- `info.startHour/endHour/startMinute/endMinute`
- `proximity_sensor.h/cpp`
- `status_bar.cpp:31/46`
- `CALL_LOG_READ_STATE::CALL_IS_READ`
- `call_status_manager.cpp:1214/1243/2262`
- `datashare:///numberlocationability`
- `datashare:///numbermarkability/number_mark_info`
- `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true`
- `datashare:///com.ohos.settingsdata.DataAbility`
- `SystemAbilityManager`
- `的文本输出同样不含任何号码或联系人字段；话单/号码展示由`
- `；检测触发/消费入口在`
- `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true&key=...`
- `GetSimState`
- `RECEIVE_UPDATE_MEDIA_MODE_REQUEST/RESPONSE`
- `UPDATE_GET/SET_WAITING`
- `UPDATE_GET/SET_RESTRICTION`
- `UPDATE_GET/SET_TRANSFER`
- `GET/SET_IMS_CONFIG`
- `GET/SET_IMS_FEATURE_VALUE`
- `input/camera_manager.h`
- `telephony_call_manager_mini/`
- `telephony_call_manager_mini/stub/`
- `XxxClient::GetInstance`
- `PublishCallManagerService`
- `VoipCallClient::GetInstance`
- `stub/cellular_call_client.h/.cpp`
- `stub/core_service_client.h/.cpp`
- `stub/cellular_data_client.h/.cpp`
- `stub/sms_client.h/.cpp`
- `stub/telephony_cust_client.h/.cpp`
- `stub/voip_call_client.h/.cpp`
- `stub/state_registry_client.h/.cpp`
- `RefPtr`
- `stub/hisysevent_stub`
- `stub/`
- `securec_stub`
- `c_utils_stub`
- `log_stub`
- `eventhandler_stub`
- `cjson_stub`
- `phonenumber_stub`
- `parameter_stub`
- `call_manager_proxy.cpp/.h`
- `motion_recognition.cpp/.h`
- `reject_call_sms.cpp/.h`
- `report_call_info_queue_`
- `stub/eventhandler_stub`
- `specs/<id>/spec.md`
- `tests/BUILD.gn`
- `stub/parameter_stub`
- `stub/cjson_stub`
- `services/audio/src/audio_state/bluetooth_device_state.cpp/.h`
- `services/audio/src/audio_state/wired_headset_device_state.cpp/.h`
- `ENABLE_DEVICE_WIRED_HEADSET/ENABLE_BLUETOOTH`
- `Telephony_AudioInit_01x`
- `Telephony_AudioEvent_01x`
- `services/audio/src/audio_state/ott_call_state.cpp/.h`
- `Telephony_AudioSceneProcessor_01x`

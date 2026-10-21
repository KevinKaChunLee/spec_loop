# JS/ETS/Cangjie Binding (JS/ETS/仓颉绑定层) Specification

## Purpose
描述 OpenHarmony v6.0 基线中 call_manager 对 JS/ETS/仓颉三方语言暴露的绑定层当前行为：napi 模块注册与拨号/接听/挂断等异步接口、事件订阅与回调上报、权限声明，以及仓颉 FFI 与 ETS taihe 绑定。源码落点：`telephony_call_manager/frameworks/js/napi/`（`src/native_module.cpp`、`src/napi_call_manager.cpp`、`src/napi_call_ability_callback.cpp`、`src/napi_call_manager_callback.cpp`、`src/napi_call_manager_utils.cpp`、`src/call.js`，头文件位于 `include/`）；仓颉绑定：`telephony_call_manager/frameworks/cj/src/`（`telephony_call_ffi.cpp`、`telephony_call_impl.cpp` 等）；ETS 绑定：`telephony_call_manager/frameworks/ets/taihe/`（`idl/ohos.telephony.call.taihe`、`src/ohos.telephony.call.impl.cpp`、`src/ani_constructor.cpp`）；类型声明：`telephony_call_manager/interfaces/kits/js/@ohos.telephony.call.d.ts`。本能力无专属编译开关（`callmanager.gni` 无 declare_args，js/cj/taihe 的 BUILD.gn 不产生 feature 宏）。

## Requirements

### Requirement: napi 模块注册与异步接口
系统 SHALL 由 `native_module.cpp` 的 `RegisterModule` 以 `nm_modname = "telephony.call"`、`nm_register_func = NapiCallManager::RegisterCallManagerFunc` 注册 napi 模块；`RegisterCallManagerFunc` 挂载 `dial`、`dialCall`、`makeCall`、`answerCall`、`hangUpCall` 等函数（`DECLARE_NAPI_FUNCTION`）与各枚举，随后调用 `Init()`（内部 `DelayedSingleton<CallManagerClient>::GetInstance()->Init(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID)`）与 `RegisterCallBack()`；每个业务接口经 `HandleAsyncWork` 异步执行——有 callbackRef 时走回调形式，无则 `napi_create_promise` 返回 Promise。

#### Scenario: dialCall 返回 Promise
- **WHEN** JS 侧调用 `telephony.call.dialCall(phoneNumber, options)` 且未传 callback
- **THEN** `NapiCallManager::DialCall` 解析号码与 `DialCallOptions` 后由 `HandleAsyncWork` 创建 Promise，工作线程执行拨号，结果以 resolve/reject 回传

#### Scenario: 参数类型不匹配抛错
- **WHEN** `dialCall` 首参不是 string（`MatchStringAndVariableObjectParameters` 失败）
- **THEN** 经 `NapiUtil::ThrowParameterError` 抛出参数错误，不创建异步工作

#### Scenario: makeCall 由 JS 层拉起联系人应用
- **WHEN** JS 侧调用 `makeCall`（`frameworks/js/napi/src/call.js` 的 `makeCallFunc`）
- **THEN** 优先 `startAbility` 拉起 `com.ohos.contacts` / `com.ohos.contacts.MainAbility`（参数含 `phoneNumber` 与 `pageFlag: 'page_flag_edit_before_calling'`），无 context 时回落调用 native `call.makeCall`

### Requirement: 事件订阅与回调上报
系统 SHALL 由 `NapiCallManager::ObserverOn(type, callback)` 按事件类型分发：`"callDetailsChange"` 注册到 `DelayedSingleton<NapiCallAbilityCallback>::GetInstance()->RegisterCallStateCallback` 并调用 `CallManagerClient::ObserverOnCallDetailsChange()`，`"audioDeviceChange"` 额外调用 `ReportAudioDeviceInfo()`，其余类型（`callEventChange`、`mmiCodeResult` 等）仅本地注册；服务侧事件经 `NapiCallManagerCallback` 转入 `NapiCallAbilityCallback` 的 `UpdateCallStateInfo`/`UpdateCallEvent` 等方法，以 `uv_queue_work_with_qos` 派发回 JS 线程执行回调。

#### Scenario: 订阅通话详情变化
- **WHEN** JS 侧调用 `telephony.call.on('callDetailsChange', callback)` 且模块已注册成功
- **THEN** 本地保存 callback 引用，并向服务端发起 `ObserverOnCallDetailsChange()` 订阅

#### Scenario: 通话状态事件异步上报
- **WHEN** 服务侧下发通话属性变化进入 `NapiCallAbilityCallback::UpdateCallStateInfo`
- **THEN** 通过 `napi_get_uv_event_loop` 取循环并以 `uv_queue_work_with_qos` 投递，JS 线程上以 `CallAttributeOptions` 形参执行用户 callback

#### Scenario: 订阅前注册失败被拒
- **WHEN** 模块 `RegisterCallBack` 失败（`registerStatus_` 非 0）后调用 `ObserverOn`
- **THEN** 不注册监听；若失败码为 `TELEPHONY_ERR_PERMISSION_ERR` 则抛出 `JS_ERROR_TELEPHONY_PERMISSION_DENIED` 对应错误

### Requirement: 权限声明与错误传递
系统 SHALL 在 `interfaces/kits/js/@ohos.telephony.call.d.ts` 中为接口标注权限：`dial`/`dialCall` 系 `ohos.permission.PLACE_CALL`，`answerCall`/`hangUpCall` 系 `ohos.permission.ANSWER_CALL`，通话设置类接口系 `ohos.permission.SET_TELEPHONY_STATE`；实际校验在 SA 侧（`CallManagerService`）执行，napi 层不重复校验，仅将返回错误码经 `NapiUtil::ConverErrorMessageForJs` 转换后以 JS 异常/错误回调抛出。

#### Scenario: 权限声明可见
- **WHEN** 读取 `@ohos.telephony.call.d.ts` 中 `dial` 与 `answerCall` 的声明
- **THEN** 分别标注 `@permission ohos.permission.PLACE_CALL` 与 `@permission ohos.permission.ANSWER_CALL`

#### Scenario: 服务端权限错误映射为 JS 异常
- **WHEN** 服务端 `DialCall` 因缺少 PLACE_CALL 权限返回 `TELEPHONY_ERR_PERMISSION_ERR`
- **THEN** napi 层将该码转换为对应 JS 错误并 reject Promise / 回调 err 参数，而不是静默失败

### Requirement: 仓颉与 ETS 绑定
系统 SHALL 提供两套非 JS 绑定：仓颉侧由 `frameworks/cj/src/telephony_call_ffi.cpp` 以 `FFI_EXPORT` 导出 `FfiOHOSTelephonyCallDialCall`、`FfiOHOSTelephonyCallMakeCall`、`FfiOHOSTelephonyCallGetCallState`、`FfiOHOSTelephonyCallHasVoiceCapability`、`FfiOHOSTelephonyCallIsEmergencyPhoneNumber` 等 C FFI（依赖 `tel_call_manager_api`）；ETS 侧由 `frameworks/ets/taihe/idl/ohos.telephony.call.taihe` IDL 生成绑定，`src/ohos.telephony.call.impl.cpp` 中 `MakeCallSync`、`HasVoiceCapability`、`FormatPhoneNumberSync` 等直接调用 `DelayedSingleton<CallManagerClient>` 对应方法，失败经 `set_business_error` 设置业务错误。

#### Scenario: 仓颉 FFI 拨号
- **WHEN** 仓颉侧调用 `FfiOHOSTelephonyCallDialCall(phoneNumber, options)`
- **THEN** FFI 转入 `CallManagerClient::DialCall`，返回值为 int32 业务码

#### Scenario: ETS makeCall 同步绑定
- **WHEN** ETS 侧调用 taihe 生成的 makeCall 绑定进入 `MakeCallSync(phoneNumber)`
- **THEN** 转调 `CallManagerClient::MakeCall`，非 `TELEPHONY_ERR_SUCCESS` 时经 `set_business_error` 抛业务错误，成功时正常返回

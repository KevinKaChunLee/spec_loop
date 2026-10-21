# Spec Delta

## REMOVED Requirements

### Requirement: napi 模块注册与异步接口
**Reason**: liteOS 上 JS/ETS/仓颉绑定的外部接口不需要实现，`frameworks/js/napi/`（`native_module.cpp`、`napi_call_manager.cpp` 等）与 `interfaces/kits` 不迁移。
**Migration**: 无替代；对外仅保留 native 客户端（client-framework 的 `CallManagerClient`）。

### Requirement: 事件订阅与回调上报
**Reason**: liteOS 上 JS/ETS/仓颉绑定的外部接口不需要实现，`NapiCallManager::ObserverOn`、`NapiCallAbilityCallback`、`NapiCallManagerCallback` 等 js/napi 回调通路不迁移。
**Migration**: 无替代；事件回调仅经进程内 native 回调通路（client-framework）下发。

### Requirement: 权限声明与错误传递
**Reason**: liteOS 上 JS/ETS/仓颉绑定的外部接口不需要实现，`interfaces/kits/js/@ohos.telephony.call.d.ts` 权限声明与 `NapiUtil::ConverErrorMessageForJs` 错误传递不迁移。
**Migration**: 无替代；liteOS 侧外部接口本身免权限校验（见 call-manager-service delta）。

### Requirement: 仓颉与 ETS 绑定
**Reason**: liteOS 上 JS/ETS/仓颉绑定的外部接口不需要实现，`frameworks/cj/`（`telephony_call_ffi.cpp` 等）与 `frameworks/ets/taihe/` 绑定不迁移。
**Migration**: 无替代；对外仅保留 native 客户端（client-framework 的 `CallManagerClient`）。
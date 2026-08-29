package com.suyuan.mobile

import android.content.Context

class AppSessionStore(context: Context) {
    private val preferences = context.getSharedPreferences("suyuan", Context.MODE_PRIVATE)

    fun token(): String = preferences.getString("token", "").orEmpty()
    fun accountId(): String = preferences.getString("account_id", "").orEmpty()
    fun displayName(): String = preferences.getString("display_name", "").orEmpty()
    fun save(result: LoginResult) {
        preferences.edit()
            .putString("token", result.token)
            .putString("account_id", result.accountId)
            .putString("display_name", result.displayName)
            .apply()
    }
    fun clear() = preferences.edit().clear().apply()
}

package com.suyuan.mobile

import android.content.Context

class AppSessionStore(context: Context) {
    private val preferences = context.getSharedPreferences("suyuan", Context.MODE_PRIVATE)

    fun token(): String = preferences.getString("token", "").orEmpty()
    fun refreshToken(): String = preferences.getString("refresh_token", "").orEmpty()
    fun expiresAt(): Long = preferences.getLong("expires_at", 0L)
    fun refreshExpiresAt(): Long = preferences.getLong("refresh_expires_at", 0L)
    fun accountId(): String = preferences.getString("account_id", "").orEmpty()
    fun displayName(): String = preferences.getString("display_name", "").orEmpty()
    fun save(result: LoginResult) {
        preferences.edit()
            .putString("token", result.token)
            .putString("refresh_token", result.refreshToken.orEmpty())
            .putLong("expires_at", result.expiresAt)
            .putLong("refresh_expires_at", result.refreshExpiresAt)
            .putString("account_id", result.accountId)
            .putString("display_name", result.displayName)
            .apply()
    }
    fun savePendingOAuth(state: String, verifier: String) {
        preferences.edit()
            .putString("oauth_state", state)
            .putString("oauth_verifier", verifier)
            .apply()
    }
    fun pendingOAuthState(): String = preferences.getString("oauth_state", "").orEmpty()
    fun pendingOAuthVerifier(): String = preferences.getString("oauth_verifier", "").orEmpty()
    fun clearPendingOAuth() = preferences.edit()
        .remove("oauth_state")
        .remove("oauth_verifier")
        .apply()
    fun clear() = preferences.edit().clear().apply()
}

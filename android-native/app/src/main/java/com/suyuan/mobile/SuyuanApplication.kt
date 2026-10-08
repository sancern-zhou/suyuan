package com.suyuan.mobile

import android.app.Application
import android.content.Context
import com.igexin.sdk.PushManager

class SuyuanApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        UnifiedPushManager.initialize(this)
    }
}

object UnifiedPushManager {
    private const val PREFS = "suyuan_push"
    private const val KEY_CID = "getui_cid"

    fun initialize(application: Application) {
        if (BuildConfig.GETUI_APPID.isBlank()) return
        runCatching {
            PushManager.getInstance().preInit(application)
            PushManager.getInstance().initialize(application)
            PushManager.getInstance().checkManifest(application)
        }
    }

    fun currentClientId(application: Application): String? {
        val cached = application.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_CID, null)
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
        return cached ?: runCatching { PushManager.getInstance().getClientid(application) }
            .getOrNull()
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
    }

    fun saveClientId(application: android.content.Context, clientId: String) {
        application.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_CID, clientId)
            .apply()
    }
}

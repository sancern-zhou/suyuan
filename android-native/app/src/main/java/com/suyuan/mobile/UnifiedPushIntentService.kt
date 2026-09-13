package com.suyuan.mobile

import android.content.Context
import android.util.Log
import com.igexin.sdk.GTIntentService
import com.igexin.sdk.message.GTTransmitMessage

/** Receives provider-neutral GeTui callbacks.  Notification messages are
 * rendered by the SDK; the App refreshes its broadcast inbox on resume. */
class UnifiedPushIntentService : GTIntentService() {
    override fun onReceiveClientId(context: Context, clientid: String) {
        UnifiedPushManager.saveClientId(context, clientid)
        Log.d(TAG, "push cid registered")
    }

    override fun onReceiveMessageData(context: Context, pushMessage: GTTransmitMessage) {
        // Keep the callback intentionally side-effect free.  The backend's
        // broadcast inbox is authoritative and is fetched by the UI.
        Log.d(TAG, "push transmission received")
    }

    companion object {
        private const val TAG = "SuyuanPush"
    }
}

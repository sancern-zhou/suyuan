package com.suyuan.mobile
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem

import android.Manifest
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.view.WindowManager
import android.os.ParcelFileDescriptor
import android.webkit.WebView
import android.widget.Toast
import java.io.File
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.draw.shadow
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.Modifier
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.pointerInteropFilter
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlin.math.roundToInt

class MainActivity : ComponentActivity() {
    private var oauthCallback by mutableStateOf<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        oauthCallback = intent?.data
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        window.statusBarColor = android.graphics.Color.BLACK
        window.navigationBarColor = android.graphics.Color.BLACK
        setContent {
            val context = LocalContext.current
            val store = remember { AppSessionStore(context) }
            val appViewModel: AppViewModel = viewModel(
                factory = AppViewModelFactory(SocialAppRepository(SocialAppApi(sessionStore = store)), store)
            )
            SuyuanApp(appViewModel, oauthCallback) { oauthCallback = null }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        oauthCallback = intent.data
    }

    companion object {
        const val NOTIFICATION_PERMISSION_REQUEST = 7001
    }
}

private class AppViewModelFactory(
    private val repository: SocialAppRepository,
    private val store: AppSessionStore,
) : androidx.lifecycle.ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : androidx.lifecycle.ViewModel> create(modelClass: Class<T>): T {
        return AppViewModel(repository, store) as T
    }
}

@Composable
private fun SuyuanApp(viewModel: AppViewModel, oauthCallback: Uri?, consumeOAuthCallback: () -> Unit) {
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner, viewModel) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.onForeground()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    LaunchedEffect(oauthCallback) {
        oauthCallback?.let {
            viewModel.handleCompanyOAuthCallback(it)
            consumeOAuthCallback()
        }
    }
    LaunchedEffect(state.loggedIn) {
        if (state.loggedIn) {
            val activity = context as? ComponentActivity
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                activity != null &&
                ContextCompat.checkSelfPermission(activity, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) {
                activity.requestPermissions(
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    MainActivity.NOTIFICATION_PERMISSION_REQUEST,
                )
            }
            val application = context.applicationContext as? android.app.Application
            repeat(10) {
                val cid = application?.let { UnifiedPushManager.currentClientId(it) }
                if (!cid.isNullOrBlank()) {
                    viewModel.registerPushDevice(cid)
                    return@LaunchedEffect
                }
                delay(1000)
            }
        }
    }
    Surface(modifier = Modifier.fillMaxSize(), color = SuyuanColors.background) {
        if (state.loggedIn) ChatScreen(state, viewModel) else LoginScreen(state, viewModel)
    }
}

@Composable
private fun LoginScreen(state: AppUiState, viewModel: AppViewModel) {
    val context = LocalContext.current
    var accountId by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    Column(
        Modifier.fillMaxSize().background(SuyuanColors.background).padding(horizontal = 28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
    ) {
        androidx.compose.foundation.Image(
            painter = painterResource(com.suyuan.mobile.R.mipmap.ic_launcher),
            contentDescription = "许昌环境Agent",
            modifier = Modifier.size(88.dp).clip(RoundedCornerShape(22.dp)),
            contentScale = ContentScale.Crop,
        )
        Text("许昌环境Agent", color = SuyuanColors.text, fontSize = 26.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 18.dp))
        Text("连接你的专属智能助手", color = SuyuanColors.secondaryText, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp, bottom = 28.dp))
        OutlinedTextField(
            accountId, { accountId = it }, Modifier.fillMaxWidth(), label = { Text("账号") },
            singleLine = true, shape = RoundedCornerShape(12.dp),
            colors = androidx.compose.material3.OutlinedTextFieldDefaults.colors(
                focusedBorderColor = SuyuanColors.primary, unfocusedBorderColor = SuyuanColors.border,
                focusedLabelColor = SuyuanColors.primary, unfocusedLabelColor = SuyuanColors.secondaryText,
            ),
        )
        OutlinedTextField(
            secret, { secret = it }, Modifier.fillMaxWidth().padding(top = 12.dp), label = { Text("访问密钥") },
            singleLine = true, shape = RoundedCornerShape(12.dp),
            colors = androidx.compose.material3.OutlinedTextFieldDefaults.colors(
                focusedBorderColor = SuyuanColors.primary, unfocusedBorderColor = SuyuanColors.border,
                focusedLabelColor = SuyuanColors.primary, unfocusedLabelColor = SuyuanColors.secondaryText,
            ),
        )
        Button(
            onClick = { viewModel.login(accountId, secret) },
            enabled = !state.loading && accountId.isNotBlank() && secret.isNotBlank(),
            modifier = Modifier.fillMaxWidth().padding(top = 24.dp).height(50.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = SuyuanColors.primary, disabledContainerColor = SuyuanColors.primary.copy(alpha = .38f)),
        ) {
            if (state.loading) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
            else Text("登录", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        }
        TextButton(
            onClick = { viewModel.startCompanyLogin(context) },
            enabled = !state.loading,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) {
            Text("公司统一登录", color = SuyuanColors.primary, fontSize = 15.sp)
        }
        state.error?.let { Text(it, color = SuyuanColors.error, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 12.dp)) }
    }
}

@Composable
@OptIn(ExperimentalComposeUiApi::class)
private fun ChatScreen(state: AppUiState, viewModel: AppViewModel) {
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current
    val focusRequester = remember { FocusRequester() }
    var recording by remember { mutableStateOf(false) }
    var voiceMode by remember { mutableStateOf(false) }
    val voicePressActive = remember { mutableStateOf(false) }
    val voiceLongPressed = remember { mutableStateOf(false) }
    val voiceGestureDownX = remember { mutableStateOf(0f) }
    val voiceGestureOffsetX = remember { mutableStateOf(0f) }
    var requestKeyboardFocus by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }
    var showHistory by remember { mutableStateOf(false) }
    var showBroadcasts by remember { mutableStateOf(false) }
    var showReports by remember { mutableStateOf(false) }
    var selectedTaskId by remember { mutableStateOf<String?>(null) }
    val voiceClient = remember { RealtimeVoiceClient(BuildConfig.API_BASE_URL) }
    DisposableEffect(voiceClient) {
        onDispose { voiceClient.stop() }
    }
    val startListening = {
        if (!recording) {
            localError = null
            recording = true
            voiceClient.start(
                token = state.token,
                onReady = { if (voicePressActive.value) recording = true },
                onText = { text, _ -> if (text.isNotBlank()) viewModel.updateDraft(text) },
                onError = { message ->
                    recording = false
                    localError = message
                },
            )
        }
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        uri?.let { viewModel.uploadAttachment(context, it) }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted && voicePressActive.value) startListening()
        else if (!granted && voicePressActive.value) localError = "需要麦克风权限"
    }
    val latestStartListening = rememberUpdatedState(startListening)
    val voiceHoldHandler = remember { Handler(Looper.getMainLooper()) }
    val voiceHoldRunnable = remember {
        Runnable {
            if (voicePressActive.value) {
                voiceLongPressed.value = true
                latestStartListening.value()
            }
        }
    }
    DisposableEffect(Unit) {
        onDispose { voiceHoldHandler.removeCallbacks(voiceHoldRunnable) }
    }
    LaunchedEffect(state.loggedIn) {
        if (state.loggedIn) {
            viewModel.onForeground()
            while (true) {
                viewModel.refreshBroadcasts(reset = false)
                delay(30_000L)
            }
        }
    }
    LaunchedEffect(requestKeyboardFocus, voiceMode) {
        if (requestKeyboardFocus && !voiceMode) {
            focusRequester.requestFocus()
            keyboardController?.show()
            requestKeyboardFocus = false
        }
    }
    val beginVoicePress = {
        voicePressActive.value = true
        voiceLongPressed.value = false
        voiceHoldHandler.removeCallbacks(voiceHoldRunnable)
        voiceHoldHandler.postDelayed(voiceHoldRunnable, 240L)
    }
    val endVoicePress = { toggleMode: Boolean ->
        voiceHoldHandler.removeCallbacks(voiceHoldRunnable)
        val wasLongPressed = voiceLongPressed.value
        voicePressActive.value = false
        localError = null
        voiceGestureOffsetX.value = 0f
        if (!wasLongPressed) {
            recording = false
            voiceClient.stop()
            if (toggleMode) {
                voiceMode = true
                keyboardController?.hide()
                focusManager.clearFocus()
            }
        } else {
            // A long-press release always sends the recognized text. Keeping
            // one outcome avoids a second gesture layer and matches the direct
            // voice-send behavior requested for the mobile app.
            // Close the recording overlay immediately; the websocket can finish
            // asynchronously without blocking the input controls.
            recording = false
            voiceClient.finish {
                voiceHoldHandler.post { viewModel.send() }
            }
        }
    }

    Box(Modifier.fillMaxSize().background(SuyuanColors.background)) {
        Column(Modifier.fillMaxSize()) {
        AppTopBar(
            showHistory = showHistory,
            showBroadcasts = showBroadcasts,
            showReports = showReports,
            taskTitles = state.scheduledTasks.map { it.taskId to it.name },
            onSelectTask = { selectedTaskId = it },
            onHistory = { showHistory = true; showBroadcasts = false; showReports = false },
            onBack = { showHistory = false; showBroadcasts = false; showReports = false },
            onBroadcasts = { showBroadcasts = true; showHistory = false; showReports = false; viewModel.openBroadcasts() },
                onReports = { selectedTaskId = null; showReports = true; showHistory = false; showBroadcasts = false; viewModel.refreshScheduledTasks() },
            unreadBroadcastCount = state.unreadBroadcastCount,
            unreadReportCount = state.reportUnreadCount,
            onNew = { showHistory = false; showBroadcasts = false; showReports = false; viewModel.newConversation() },
        )
        if (showReports) {
            ScheduledTaskPanel(state, viewModel, selectedTaskId, onSession = { showReports = false })
        } else if (showBroadcasts) {
            BroadcastPanel(state, viewModel, onBack = { showBroadcasts = false })
        } else if (showHistory) {
            HistoryPanel(state, viewModel, onBack = { showHistory = false })
        } else Column(Modifier.fillMaxSize()) {
            if (state.unreadBroadcastCount > 0) {
                Surface(
                    color = SuyuanColors.primary.copy(alpha = .08f),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.padding(horizontal = 12.dp).fillMaxWidth().padding(top = 6.dp).clickable { showBroadcasts = true; viewModel.openBroadcasts() },
                ) {
                    Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Icon(painterResource(R.drawable.ic_broadcast), contentDescription = null, tint = SuyuanColors.primary, modifier = Modifier.size(18.dp))
                        Text("收到 ${state.unreadBroadcastCount} 条广播消息", color = SuyuanColors.primary, fontSize = 13.sp, modifier = Modifier.padding(start = 7.dp))
                    }
                }
            }
            val conversationListState = rememberLazyListState()
            val visibleMessages = state.messages.filterNot { it.kind == "thought" }
            val showingWorkStatus = state.workStatus != null
            var initiallyScrolledSession by remember { mutableStateOf<String?>(null) }
            LaunchedEffect(state.messages.size, state.messages.lastOrNull()?.content?.length, state.messages.lastOrNull()?.kind, showingWorkStatus, state.pendingInteraction?.interactionId) {
                if (state.messages.isNotEmpty()) {
                    val lastIndex = visibleMessages.lastIndex
                    val visibleLast = conversationListState.layoutInfo.visibleItemsInfo.lastOrNull()?.index
                    val lastMessageIsNewUserInput = state.messages.lastOrNull()?.kind == "user"
                    val targetIndex = lastIndex + (if (showingWorkStatus) 1 else 0) + (if (state.pendingInteraction != null) 1 else 0)
                    val isFirstRestore = !state.sessionId.isNullOrBlank() && initiallyScrolledSession != state.sessionId
                    if (isFirstRestore || lastMessageIsNewUserInput || visibleLast == null || visibleLast >= lastIndex - 1) {
                        conversationListState.scrollToItem(targetIndex)
                    }
                    if (isFirstRestore) initiallyScrolledSession = state.sessionId
                }
            }
            LazyColumn(
                state = conversationListState,
                modifier = Modifier.weight(1f).fillMaxWidth().padding(top = 4.dp)
                    .pointerInput(Unit) { detectTapGestures(onTap = { keyboardController?.hide(); focusManager.clearFocus() }) },
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(vertical = 8.dp),
            ) {
                if (state.messages.isEmpty()) {
                    item { EmptyChatState(loading = state.loading, mode = state.mode, onModeSelected = viewModel::selectMode) }
                } else items(visibleMessages, key = { it.id }) {
                    ChatMessageView(it, state, viewModel)
                }
                state.pendingInteraction?.let { question ->
                    item(key = "question-${question.interactionId}") {
                        AgentQuestionCard(question, state.loading, state.questionSubmitting, state.error,
                            onSubmit = { viewModel.resolveQuestion("answer", it) },
                            onCancel = { viewModel.resolveQuestion("reject") })
                    }
                }
                if (showingWorkStatus) {
                    item(key = "working-status") {
                        WorkingStatusIndicator(state.workStatus.orEmpty(), state.mode, state.workStartedAtMs)
                    }
                }
            }
        val canCancel = state.loading && state.sessionId != null
        if (state.attachments.isNotEmpty()) {
            Column(Modifier.padding(horizontal = 12.dp)) { AttachmentTray(state, viewModel, context) }
        }
        Surface(
            color = Color.White,
            shape = RoundedCornerShape(22.dp),
            tonalElevation = 0.dp,
            modifier = Modifier.padding(horizontal = 12.dp).fillMaxWidth()
                .shadow(8.dp, RoundedCornerShape(22.dp), ambientColor = Color(0x22000000), spotColor = Color(0x18000000))
                .border(1.dp, Color(0xFFE7E9EE), RoundedCornerShape(22.dp))
                .padding(vertical = 8.dp)
                .imePadding()
                .navigationBarsPadding(),
        ) {
            Column {
            Row(
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            ) {
                val voiceEnabled = state.loggedIn || recording
                fun handleVoiceEvent(event: android.view.MotionEvent, toggleOnTap: Boolean): Boolean {
                    return when (event.actionMasked) {
                        android.view.MotionEvent.ACTION_DOWN -> {
                            voicePressActive.value = true
                            voiceGestureDownX.value = event.rawX
                            voiceGestureOffsetX.value = 0f
                            if (voiceEnabled && !recording) {
                                if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                                    permission.launch(Manifest.permission.RECORD_AUDIO)
                                }
                                beginVoicePress()
                            }
                            true
                        }
                        android.view.MotionEvent.ACTION_MOVE -> {
                            if (voiceLongPressed.value) {
                                val offset = (event.rawX - voiceGestureDownX.value).coerceIn(-260f, 260f)
                                voiceGestureOffsetX.value = offset
                            }
                            true
                        }
                        android.view.MotionEvent.ACTION_UP,
                        android.view.MotionEvent.ACTION_CANCEL -> {
                            endVoicePress(toggleOnTap)
                            true
                        }
                        else -> true
                }
                }
                if (!voiceMode) {
                    Box(
                        Modifier.size(30.dp).clip(CircleShape)
                            .border(1.5.dp, if (recording) SuyuanColors.error else SuyuanColors.controlIcon, CircleShape)
                            .pointerInteropFilter { handleVoiceEvent(it, toggleOnTap = true) },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(
                            painterResource(R.drawable.ic_voice_right),
                            contentDescription = if (recording) "松开停止" else "按住切换语音输入",
                            tint = if (recording) SuyuanColors.error else SuyuanColors.controlIcon,
                            modifier = Modifier.size(16.dp),
                        )
                    }
                    BasicTextField(
                        value = state.draft,
                        onValueChange = viewModel::updateDraft,
                        modifier = Modifier.weight(1f).heightIn(min = 40.dp, max = 72.dp).focusRequester(focusRequester),
                        enabled = true,
                        minLines = 1,
                        maxLines = 4,
                        textStyle = TextStyle(color = SuyuanColors.text, fontSize = 16.sp, lineHeight = 21.sp),
                        cursorBrush = SolidColor(SuyuanColors.primary),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = {
                            if (!recording && state.draft.isNotBlank()) viewModel.send()
                        }),
                        decorationBox = { innerTextField ->
                            Box(
                                Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(SuyuanColors.panel)
                                    .padding(horizontal = 12.dp, vertical = 7.dp),
                                contentAlignment = androidx.compose.ui.Alignment.CenterStart,
                            ) {
                                if (state.draft.isBlank()) Text("输入消息...", color = SuyuanColors.secondaryText, fontSize = 16.sp)
                                innerTextField()
                            }
                        },
                    )
                    Box(
                        Modifier.size(30.dp).clip(CircleShape)
                            .border(1.5.dp, SuyuanColors.controlIcon, CircleShape)
                            .clickable { picker.launch("*/*") },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(painterResource(R.drawable.ic_plus), contentDescription = "添加附件", tint = SuyuanColors.controlIcon, modifier = Modifier.size(16.dp))
                    }
                    if (canCancel || state.draft.isNotBlank()) {
                        val hasDraft = state.draft.isNotBlank()
                        val actionEnabled = !recording && (hasDraft || canCancel)
                        Box(
                            Modifier.size(30.dp).clip(CircleShape)
                                .background(if (actionEnabled) SuyuanColors.primary else Color.Transparent)
                                .border(1.5.dp, if (actionEnabled) SuyuanColors.primary else SuyuanColors.border, CircleShape)
                                .clickable(enabled = actionEnabled) { if (hasDraft) viewModel.send() else viewModel.cancel() },
                            contentAlignment = androidx.compose.ui.Alignment.Center,
                        ) {
                            Icon(
                                painterResource(if (hasDraft) R.drawable.ic_arrow_up else R.drawable.ic_stop),
                                contentDescription = if (hasDraft) "发送" else "取消生成",
                                tint = if (actionEnabled) Color.White else SuyuanColors.controlIcon,
                                modifier = Modifier.size(16.dp),
                            )
                        }
                    }
                } else {
                    Box(
                        Modifier.size(30.dp).clip(CircleShape)
                            .border(1.5.dp, SuyuanColors.controlIcon, CircleShape)
                            .clickable(enabled = !recording) { voiceMode = false },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(painterResource(R.drawable.ic_keyboard), contentDescription = "切换键盘输入", tint = SuyuanColors.controlIcon, modifier = Modifier.size(16.dp))
                    }
                    Box(
                        Modifier.weight(1f).height(40.dp).clip(RoundedCornerShape(12.dp))
                            .background(if (recording) SuyuanColors.error.copy(alpha = .12f) else SuyuanColors.panel)
                            .border(1.dp, if (recording) SuyuanColors.error else SuyuanColors.border, RoundedCornerShape(12.dp))
                            .pointerInteropFilter { handleVoiceEvent(it, toggleOnTap = false) },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Text(if (recording) "松开停止" else "按住说话", color = if (recording) SuyuanColors.error else SuyuanColors.text, fontSize = 15.sp)
                    }
                    Box(
                        Modifier.size(30.dp).clip(CircleShape)
                            .border(1.5.dp, SuyuanColors.controlIcon, CircleShape)
                            .clickable { picker.launch("*/*") },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(painterResource(R.drawable.ic_plus), contentDescription = "添加附件", tint = SuyuanColors.controlIcon, modifier = Modifier.size(16.dp))
                    }
                }
            }
            Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 2.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("auto" to "自动", "fast" to "快速模式", "deep" to "深度思考").forEach { (tier, label) ->
                    val selected = state.modelTier == tier
                    Text(label, color = if (selected) SuyuanColors.primary else SuyuanColors.secondaryText, fontSize = 12.sp,
                        modifier = Modifier.clip(RoundedCornerShape(16.dp)).background(if (selected) SuyuanColors.primary.copy(alpha = .12f) else Color.Transparent)
                            .border(1.dp, if (selected) SuyuanColors.primary.copy(alpha = .4f) else SuyuanColors.border, RoundedCornerShape(16.dp))
                            .clickable { viewModel.selectModelTier(tier) }.padding(horizontal = 12.dp, vertical = 6.dp))
                }
            }
            }
        }
        (state.error ?: localError)?.let { Text(it, color = SuyuanColors.error, fontSize = 13.sp, modifier = Modifier.padding(bottom = 8.dp)) }
        }
    }
        if (recording) VoiceRecordingOverlay(voiceGestureOffsetX.value)
    }
}

@Composable
private fun VoiceRecordingOverlay(offsetX: Float) {
    Box(
        Modifier.fillMaxSize().background(Color.Black.copy(alpha = .72f)),
        contentAlignment = androidx.compose.ui.Alignment.BottomCenter,
    ) {
        Column(
            Modifier.fillMaxSize().padding(horizontal = 24.dp, vertical = 22.dp),
            horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.weight(1f))
            Surface(
                color = Color(0xFF8FEF63),
                shape = RoundedCornerShape(18.dp),
                modifier = Modifier.width(210.dp).height(84.dp).offset { IntOffset((offsetX * 0.12f).roundToInt(), 0) },
            ) {
                Row(
                    Modifier.fillMaxSize().padding(horizontal = 34.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                ) {
                    val heights = listOf(6, 10, 16, 24, 13, 28, 18, 10, 21, 13, 7)
                    heights.forEach { height ->
                        Box(Modifier.padding(horizontal = 1.5.dp).width(3.dp).height(height.dp).clip(RoundedCornerShape(3.dp)).background(Color(0xFF3A6A31)))
                    }
                }
            }
            Text(
                "松开发送语音文字",
                color = Color.White,
                fontSize = 17.sp,
                modifier = Modifier.padding(top = 14.dp),
            )
            Spacer(Modifier.weight(1f))
        }
    }
}

@Composable
private fun AppTopBar(
    showHistory: Boolean,
    showBroadcasts: Boolean,
    showReports: Boolean,
    taskTitles: List<Pair<String, String>>,
    onSelectTask: (String) -> Unit,
    onHistory: () -> Unit,
    onBack: () -> Unit,
    onBroadcasts: () -> Unit,
    onReports: () -> Unit,
    unreadBroadcastCount: Int,
    unreadReportCount: Int,
    onNew: () -> Unit,
) {
    var taskMenuExpanded by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().background(Color.White).statusBarsPadding().padding(horizontal = 18.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
            IconButton(onClick = if (showHistory || showBroadcasts || showReports) onBack else onHistory) {
                Icon(painterResource(if (showHistory || showBroadcasts || showReports) R.drawable.ic_back else R.drawable.ic_menu), contentDescription = if (showHistory || showBroadcasts || showReports) "返回对话" else "历史会话", tint = SuyuanColors.text)
            }
            if (showHistory) Text("历史会话", color = SuyuanColors.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp))
            if (showBroadcasts) {
                Text("广播消息", color = SuyuanColors.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp))
            } else if (showReports) {
                Icon(painterResource(R.drawable.ic_history), contentDescription = null, tint = SuyuanColors.primary, modifier = Modifier.size(22.dp))
                Text("定时任务", color = SuyuanColors.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp))
            } else if (!showHistory) {
                Box {
                    IconButton(onClick = onBroadcasts) {
                        Icon(painterResource(R.drawable.ic_broadcast), contentDescription = "广播消息", tint = SuyuanColors.text)
                    }
                    if (unreadBroadcastCount > 0) {
                        Box(Modifier.size(8.dp).clip(CircleShape).background(SuyuanColors.error).align(androidx.compose.ui.Alignment.TopEnd))
                    }
                }
                IconButton(onClick = onReports) {
                    Box {
                        Icon(painterResource(R.drawable.ic_history), contentDescription = "定时任务", tint = SuyuanColors.text)
                        if (unreadReportCount > 0) Box(Modifier.size(8.dp).clip(CircleShape).background(SuyuanColors.error).align(androidx.compose.ui.Alignment.TopEnd))
                    }
                }
            }
        }
        if (showReports) {
            Box {
                IconButton(onClick = { taskMenuExpanded = true }) {
                    Icon(painterResource(R.drawable.ic_menu), contentDescription = "切换任务", tint = SuyuanColors.text)
                }
                DropdownMenu(expanded = taskMenuExpanded, onDismissRequest = { taskMenuExpanded = false }) {
                    taskTitles.forEach { (id, title) ->
                        DropdownMenuItem(text = { Text(title) }, onClick = { onSelectTask(id); taskMenuExpanded = false })
                    }
                }
            }
        } else if (!showBroadcasts) IconButton(onClick = onNew) {
            Icon(painterResource(R.drawable.ic_new_chat), contentDescription = "新建对话", tint = SuyuanColors.text, modifier = Modifier.size(28.dp))
        }
    }
}

@Composable
private fun HistoryPanel(state: AppUiState, viewModel: AppViewModel, onBack: () -> Unit) {
    var actionSession by remember { mutableStateOf<SessionInfo?>(null) }
    var renameSession by remember { mutableStateOf<SessionInfo?>(null) }
    var deleteSession by remember { mutableStateOf<SessionInfo?>(null) }
    var renameTitle by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    LaunchedEffect(listState, state.sessions.size, state.sessionsHasMore) {
        snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1 }
            .distinctUntilChanged()
            .collect { lastIndex ->
                if (lastIndex >= state.sessions.size - 2) viewModel.loadMoreSessions()
            }
    }
    LazyColumn(state = listState, modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
        items(state.sessions) { session ->
            Surface(
                color = Color.White,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp).clickable { viewModel.loadSession(session); onBack() },
            ) {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 15.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Icon(painterResource(R.drawable.ic_history), contentDescription = null, tint = SuyuanColors.primary, modifier = Modifier.size(22.dp))
                    Column(Modifier.padding(start = 12.dp).weight(1f)) {
                        Text(session.title, color = SuyuanColors.text, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                        session.updatedAt?.let { updatedAt ->
                            Text(updatedAt.replace('T', ' ').take(16), color = SuyuanColors.secondaryText, fontSize = 11.sp, maxLines = 1)
                        }
                    }
                    Text(if (session.sessionId == state.sessionId) "当前" else "", color = SuyuanColors.primary, fontSize = 12.sp)
                    IconButton(onClick = { actionSession = session }) {
                        Icon(painterResource(R.drawable.ic_more), contentDescription = "会话操作", tint = SuyuanColors.secondaryText)
                    }
                }
            }
        }
        if (state.sessions.isEmpty()) {
            item {
                Text("暂无历史会话", color = SuyuanColors.secondaryText, fontSize = 14.sp, modifier = Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 8.dp))
            }
        } else if (state.sessionsLoadingMore) {
            item {
                Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = androidx.compose.ui.Alignment.Center) {
                    CircularProgressIndicator(color = SuyuanColors.primary, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
                }
            }
        }
    }
    actionSession?.let { session ->
        AlertDialog(
            onDismissRequest = { actionSession = null },
            title = { Text(session.title) },
            text = {
                Column {
                    TextButton(onClick = {
                        renameTitle = session.title
                        renameSession = session
                        actionSession = null
                    }) { Text("重命名") }
                    TextButton(onClick = {
                        deleteSession = session
                        actionSession = null
                    }) { Text("删除", color = SuyuanColors.error) }
                }
            },
            confirmButton = { TextButton(onClick = { actionSession = null }) { Text("取消") } },
        )
    }
    renameSession?.let { session ->
        AlertDialog(
            onDismissRequest = { renameSession = null },
            title = { Text("重命名会话") },
            text = {
                OutlinedTextField(value = renameTitle, onValueChange = { renameTitle = it }, singleLine = true, label = { Text("会话名称") })
            },
            confirmButton = {
                TextButton(onClick = { viewModel.renameSession(session, renameTitle); renameSession = null }, enabled = renameTitle.trim().isNotBlank()) { Text("保存") }
            },
            dismissButton = { TextButton(onClick = { renameSession = null }) { Text("取消") } },
        )
    }
    deleteSession?.let { session ->
        AlertDialog(
            onDismissRequest = { deleteSession = null },
            title = { Text("删除会话") },
            text = { Text("确定删除“${session.title}”及其历史消息吗？") },
            confirmButton = { TextButton(onClick = { viewModel.deleteSession(session); deleteSession = null }) { Text("删除", color = SuyuanColors.error) } },
            dismissButton = { TextButton(onClick = { deleteSession = null }) { Text("取消") } },
        )
    }
}

@Composable
private fun BroadcastPanel(state: AppUiState, viewModel: AppViewModel, onBack: () -> Unit) {
    var expandedMessageId by rememberSaveable { mutableStateOf<String?>(null) }
    var query by rememberSaveable { mutableStateOf("") }
    var unreadOnly by rememberSaveable { mutableStateOf(false) }
    var deleteMessage by remember { mutableStateOf<BroadcastMessage?>(null) }
    val listState = rememberLazyListState()
    LaunchedEffect(listState, state.broadcastMessages.size, state.broadcastHasMore) {
        snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1 }
            .distinctUntilChanged()
            .collect { lastIndex ->
                if (lastIndex >= state.broadcastMessages.size - 2) viewModel.loadMoreBroadcasts()
            }
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        Row(Modifier.fillMaxWidth().padding(bottom = 6.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            OutlinedTextField(query, { query = it }, singleLine = true, label = { Text("搜索广播") }, modifier = Modifier.weight(1f))
            TextButton(onClick = { unreadOnly = !unreadOnly }) { Text(if (unreadOnly) "全部" else "未读", color = SuyuanColors.primary, fontSize = 12.sp) }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            if (state.broadcastMessages.any { !it.read }) {
                TextButton(onClick = { viewModel.markAllBroadcastsRead() }) { Text("全部已读", color = SuyuanColors.primary, fontSize = 12.sp) }
            }
        }
        if (state.broadcastLoading && state.broadcastMessages.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) { CircularProgressIndicator(color = SuyuanColors.primary, strokeWidth = 2.dp) }
        } else if (state.broadcastError != null && state.broadcastMessages.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                Text(state.broadcastError, color = SuyuanColors.error, fontSize = 14.sp)
            }
        } else if (state.broadcastMessages.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) { Text("暂无广播消息", color = SuyuanColors.secondaryText, fontSize = 15.sp) }
        } else {
            val filteredMessages = state.broadcastMessages.filter { (!unreadOnly || !it.read) && (query.isBlank() || it.content.contains(query, ignoreCase = true)) }
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 16.dp),
            ) {
                items(filteredMessages, key = { it.messageId }) { broadcast ->
                    val expanded = expandedMessageId == broadcast.messageId
                    Surface(
                        color = if (expanded) SuyuanColors.panel else Color.White,
                        shape = RoundedCornerShape(12.dp),
                        tonalElevation = 1.dp,
                        modifier = Modifier.fillMaxWidth().clickable {
                            expandedMessageId = if (expanded) null else broadcast.messageId
                            viewModel.markBroadcastRead(broadcast)
                        },
                    ) {
                        Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                                if (!broadcast.read) {
                                    Text("未读", color = SuyuanColors.primary, fontSize = 12.sp)
                                }
                                Spacer(Modifier.weight(1f))
                                broadcast.timestamp?.let { Text(it.replace('T', ' ').take(16), color = SuyuanColors.secondaryText, fontSize = 11.sp) }
                                IconButton(onClick = { deleteMessage = broadcast }) {
                                    Icon(painterResource(R.drawable.ic_more), contentDescription = "广播消息操作", tint = SuyuanColors.secondaryText)
                                }
                            }
                            if (expanded) {
                                if (broadcast.content.isNotBlank()) {
                                    MarkdownContent(broadcast.content, SuyuanColors.text, state, viewModel)
                                }
                                broadcast.attachments.forEach { attachment ->
                                    AttachmentView(attachment, state, viewModel, LocalContext.current)
                                }
                            } else {
                                Text(
                                    broadcast.content.replace(Regex("\\s+"), " ").trim(),
                                    color = SuyuanColors.text,
                                    fontSize = 14.sp,
                                    lineHeight = 20.sp,
                                    maxLines = 2,
                                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                                    modifier = Modifier.padding(top = 8.dp),
                                )
                                if (broadcast.attachments.isNotEmpty()) {
                                    Text(
                                        "附件 ${broadcast.attachments.size} 个",
                                        color = SuyuanColors.secondaryText,
                                        fontSize = 11.sp,
                                        modifier = Modifier.padding(top = 6.dp),
                                    )
                                }
                            }
                        }
                    }
                }
                if (state.broadcastLoadingMore) {
                    item(key = "broadcast-loading") {
                        Box(Modifier.fillMaxWidth().padding(vertical = 8.dp), contentAlignment = androidx.compose.ui.Alignment.Center) {
                            CircularProgressIndicator(color = SuyuanColors.primary, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
                        }
                    }
                }
            }
        }
    }
    deleteMessage?.let { message ->
        AlertDialog(
            onDismissRequest = { deleteMessage = null },
            title = { Text("删除广播消息") },
            text = { Text("确定删除这条广播消息吗？删除后无法恢复。") },
            confirmButton = {
                TextButton(onClick = { viewModel.deleteBroadcast(message); deleteMessage = null }) {
                    Text("删除", color = SuyuanColors.error)
                }
            },
            dismissButton = { TextButton(onClick = { deleteMessage = null }) { Text("取消") } },
        )
    }
}

@Composable
private fun EmptyChatState(loading: Boolean = false, mode: String = "query", onModeSelected: (String) -> Unit = {}) {
    Column(Modifier.fillMaxWidth().padding(top = 110.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
        Text(if (loading) "正在恢复会话" else modeTitle(mode), color = SuyuanColors.text, fontSize = 22.sp, fontWeight = FontWeight.Medium)
        Row(Modifier.padding(top = 22.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("query" to "问数生图", "knowledge" to "知识问答", "expert" to "专家模式").forEach { (key, label) ->
                Surface(
                    color = if (mode == key) SuyuanColors.primary.copy(alpha = .22f) else SuyuanColors.panel,
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.clickable { onModeSelected(key) },
                ) { Text(label, color = if (mode == key) SuyuanColors.primary else SuyuanColors.text, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp)) }
            }
        }
        Text(
            if (loading) "正在加载最近的会话内容…" else "向许昌环境Agent 描述你想完成的任务",
            color = SuyuanColors.secondaryText,
            fontSize = 13.sp,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
}

@Composable
private fun WorkingStatusIndicator(status: String, mode: String, startedAtMs: Long?) {
    var elapsedSeconds by remember(startedAtMs) { mutableIntStateOf(0) }
    LaunchedEffect(startedAtMs) {
        while (startedAtMs != null) {
            elapsedSeconds = ((android.os.SystemClock.elapsedRealtime() - startedAtMs) / 1000L).coerceAtLeast(0).toInt()
            delay(1000)
        }
    }
    val transition = rememberInfiniteTransition(label = "work-status")
    val dotAlpha by transition.animateFloat(
        initialValue = .35f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(600), RepeatMode.Reverse),
        label = "work-status-dot",
    )
    val tips = progressTips(mode)
    val tip = if (elapsedSeconds < 6 || tips.isEmpty()) "" else {
        val rotation = (elapsedSeconds - 6) / 10
        tips[(rotation + (mode.hashCode() and Int.MAX_VALUE)) % tips.size]
    }
    Row(
        Modifier.fillMaxWidth().padding(start = 8.dp, top = 4.dp, end = 8.dp, bottom = 8.dp),
        verticalAlignment = androidx.compose.ui.Alignment.Top,
    ) {
        Box(Modifier.padding(top = 6.dp).size(9.dp).clip(CircleShape).background(SuyuanColors.secondaryText.copy(alpha = dotAlpha)))
        Column(Modifier.padding(start = 9.dp)) {
            Column {
                Text(status, color = SuyuanColors.text, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Text(formatWorkElapsed(elapsedSeconds), color = SuyuanColors.secondaryText, fontSize = 11.sp, modifier = Modifier.padding(start = 8.dp, bottom = 1.dp))
            }
            if (tip.isNotBlank()) {
                Text("小技巧  $tip", color = SuyuanColors.secondaryText, fontSize = 11.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 4.dp))
            }
        }
    }
}

private fun formatWorkElapsed(seconds: Int): String {
    if (seconds < 60) return "已进行 ${seconds} 秒"
    val minutes = seconds / 60
    val rest = seconds % 60
    return if (rest == 0) "已进行 ${minutes} 分" else "已进行 ${minutes} 分 ${rest} 秒"
}

private fun progressTips(mode: String): List<String> {
    val modeTips = when (mode) {
        "query" -> listOf("指定时间范围、区域、指标和统计口径，查询结果会更准确", "需要对比分析时，可以同时说明基准时段和排序方式")
        "knowledge" -> listOf("指定知识库、文档或章节范围，可以减少无关检索", "需要核验结论时，可以要求同时给出原文依据")
        else -> listOf("说明决策场景和约束条件，有助于获得更可执行的建议", "复杂研判可以要求区分事实、推断和不确定性")
    }
    return modeTips + listOf(
        "说明目标、可用资料和输出格式，Agent 会更快对齐需求",
        "复杂任务可以分步提出，先确认方向再继续完善",
        "提供一个满意的参考样例，通常比抽象描述更有效",
        "日常查询可用快速模式，复杂研判建议使用深度思考",
    )
}

private fun modeTitle(mode: String): String = when (mode) {
    "query" -> "问数生图模式开始对话"
    "knowledge" -> "知识问答模式开始对话"
    else -> "专家模式开始对话"
}

@Composable
private fun StreamingCursor() {
    val transition = rememberInfiniteTransition()
    val alpha by transition.animateFloat(
        initialValue = 1f,
        targetValue = 0.12f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 520),
            repeatMode = RepeatMode.Reverse,
        ),
    )
    Text("|", color = SuyuanColors.primary.copy(alpha = alpha), fontSize = 15.sp)
}

@Composable
private fun ChatMessageView(message: ChatMessage, state: AppUiState, viewModel: AppViewModel) {
    val context = LocalContext.current
    val isUser = message.kind == "user"
    val horizontal = if (isUser) Arrangement.End else Arrangement.Start
    Row(Modifier.fillMaxWidth().padding(horizontal = if (isUser) 12.dp else 0.dp, vertical = 4.dp), horizontalArrangement = horizontal) {
        val bubbleShape = RoundedCornerShape(18.dp)
        val messageModifier = Modifier
            .then(if (isUser) Modifier.widthIn(max = 330.dp) else Modifier.fillMaxWidth())
            .then(
                if (isUser) {
                    Modifier
                        .clip(bubbleShape)
                        .background(Color.Transparent)
                        .border(1.dp, SuyuanColors.primary.copy(alpha = .42f), bubbleShape)
                } else Modifier
            )
            .padding(horizontal = if (isUser) 14.dp else 0.dp, vertical = 7.dp)
        Column(messageModifier) {
            when (message.kind) {
                "thought" -> {
                    val thoughtShape = RoundedCornerShape(10.dp)
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(thoughtShape)
                            .background(SuyuanColors.panel.copy(alpha = .72f))
                            .border(1.dp, SuyuanColors.border, thoughtShape),
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { viewModel.toggleThought(message.id) }
                                .padding(horizontal = 10.dp, vertical = 8.dp),
                            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                        ) {
                            Icon(
                                painterResource(if (message.expanded) R.drawable.ic_chevron_down else R.drawable.ic_chevron_right),
                                contentDescription = if (message.expanded) "收起思考过程" else "展开思考过程",
                                tint = SuyuanColors.secondaryText,
                                modifier = Modifier.size(18.dp),
                            )
                            Text("思考过程", color = SuyuanColors.secondaryText, fontSize = 13.sp, modifier = Modifier.padding(start = 4.dp).weight(1f))
                            Text(
                                when {
                                    message.streaming -> "生成中…"
                                    message.expanded -> "收起"
                                    else -> "展开"
                                },
                                color = if (message.streaming) SuyuanColors.secondaryText else SuyuanColors.primary,
                                fontSize = 12.sp,
                            )
                        }
                        if (message.expanded) {
                            SelectionContainer {
                                Text(
                                    message.content,
                                    color = SuyuanColors.secondaryText,
                                    fontSize = 13.sp,
                                    lineHeight = 19.sp,
                                    modifier = Modifier.padding(start = 32.dp, end = 10.dp, bottom = 10.dp),
                                )
                            }
                        }
                    }
                }
                "tool" -> {
                    SelectionContainer {
                        Text(message.content, color = SuyuanColors.secondaryText, fontSize = 12.sp)
                    }
                    message.attachments.forEach { attachment -> AttachmentView(attachment, state, viewModel, context) }
                }
                "error" -> SelectionContainer {
                    Text(message.content, color = SuyuanColors.error, fontSize = 13.sp, lineHeight = 19.sp)
                }
                else -> {
                    Column(Modifier.padding(horizontal = if (isUser) 0.dp else 14.dp)) { ProcessSummary(message) }
                    val blocks = if (isUser) listOf(ReplyBlock.Text(message.content)) else chartReplyBlocks(message.content, message.attachments)
                    if (message.content.isNotBlank()) {
                        blocks.forEach { block ->
                            when (block) {
                                is ReplyBlock.Text -> Column(Modifier.padding(horizontal = if (isUser) 0.dp else 14.dp)) {
                                    MarkdownContent(block.content, if (isUser) SuyuanColors.primary else SuyuanColors.text, state, viewModel)
                                }
                                is ReplyBlock.Chart -> InlineChart(block.attachment, state, viewModel)
                                is ReplyBlock.Image -> AttachmentView(block.attachment, state, viewModel, context, inlineImage = true)
                            }
                        }
                    }
                    if (message.streaming) {
                        // A blinking cursor keeps the streaming state visible during quiet intervals.
                        StreamingCursor()
                    }
                    val placedCharts = blocks.mapNotNull {
                        when (it) {
                            is ReplyBlock.Chart -> it.attachment.fileId
                            is ReplyBlock.Image -> it.attachment.fileId
                            else -> null
                        }
                    }.toSet()
                    if (isUser) message.attachments.forEach { AttachmentView(it, state, viewModel, context) }
                    else if (!message.streaming) ReplyOutcomeCards(message.attachments, placedCharts, state, viewModel)
                }
            }
        }
    }
}

@Composable
private fun ProcessSummary(message: ChatMessage) {
    if (message.kind != "assistant" || (message.durationMs == null && message.toolCount == 0)) return
    val duration = message.durationMs?.let { if (it < 1000) "${it}毫秒" else "${"%.1f".format(it / 1000.0)}秒" }
    Text(
        "${duration?.let { "用时${it}完成" } ?: "已完成"} · ${message.toolCount}个工具调用",
        color = SuyuanColors.secondaryText,
        fontSize = 12.sp,
        modifier = Modifier.padding(bottom = 6.dp),
    )
}

private sealed class MarkdownBlock {
    data class Text(val value: String) : MarkdownBlock()
    data class Table(val headers: List<String>, val rows: List<List<String>>) : MarkdownBlock()
    data class Image(val url: String, val alt: String) : MarkdownBlock()
}

private val MARKDOWN_IMAGE_LINE_RE = Regex("^!\\[([^\\]]*)\\]\\(([^)\\s]+)\\)\\s*$")

@Composable
internal fun MarkdownContent(
    content: String,
    color: Color,
    state: AppUiState? = null,
    viewModel: AppViewModel? = null,
) {
    SelectionContainer {
        Column {
            parseMarkdownBlocks(content).forEach { block ->
                when (block) {
                    is MarkdownBlock.Text -> if (block.value.isNotBlank()) {
                        Text(remember(block.value) { markdownToAnnotatedString(block.value) }, color = color, fontSize = 15.sp, lineHeight = 22.sp)
                    }
                    is MarkdownBlock.Table -> MarkdownTable(block.headers, block.rows, color)
                    is MarkdownBlock.Image -> MarkdownImage(block.url, block.alt, state, viewModel)
                }
            }
        }
    }
}

@Composable
private fun MarkdownImage(url: String, alt: String, state: AppUiState?, viewModel: AppViewModel?) {
    if (state == null || viewModel == null) return
    // markdown 图片与 [[chart:<id>]] 图片共用附件预览通道（带 token 下载/缓存）。
    val key = "mdimg:$url"
    LaunchedEffect(url) {
        viewModel.loadAttachmentPreview(
            UploadedAttachment(
                fileId = key,
                filename = url.substringAfterLast('/').ifBlank { "image.png" },
                fileType = "image",
                mimeType = "image/png",
                url = url,
                resourceRef = null,
            )
        )
    }
    val preview = state.attachmentPreviews[key]
    val loadError = preview?.error
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        val bytes = preview?.imageBytes
        val bitmap = remember(bytes) { bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size) } }
        when {
            bitmap != null -> androidx.compose.foundation.Image(
                bitmap = bitmap.asImageBitmap(),
                contentDescription = alt.ifBlank { "图片" },
                modifier = Modifier.fillMaxWidth(),
                contentScale = ContentScale.FillWidth,
            )
            loadError != null -> Text("图片加载失败：$loadError", color = SuyuanColors.error, fontSize = 13.sp)
            else -> Text("图片加载中…", color = SuyuanColors.secondaryText, fontSize = 13.sp)
        }
        if (alt.isNotBlank()) {
            Text(alt, color = SuyuanColors.secondaryText, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun MarkdownTable(headers: List<String>, rows: List<List<String>>, color: Color) {
    val columnCount = maxOf(headers.size, rows.maxOfOrNull { it.size } ?: 0)
    if (columnCount == 0) return

    val normalizedHeaders = List(columnCount) { headers.getOrNull(it).orEmpty() }
    val normalizedRows = rows.map { row -> List(columnCount) { row.getOrNull(it).orEmpty() } }
    val columnWidths = remember(normalizedHeaders, normalizedRows) {
        List(columnCount) { index ->
            val maxChars = (listOf(normalizedHeaders[index]) + normalizedRows.map { it[index] })
                .maxOfOrNull(::estimatedTableCellLength)
                ?: 1
            ((maxChars * 7) + 28).coerceIn(108, 220).dp
        }
    }
    val tableWidth = columnWidths.fold(0.dp) { total, width -> total + width }

    Column(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 6.dp)) {
        MarkdownTableRow(normalizedHeaders, columnWidths, tableWidth, color, header = true, rowIndex = 0)
        normalizedRows.forEachIndexed { rowIndex, row ->
            MarkdownTableRow(row, columnWidths, tableWidth, color, header = false, rowIndex = rowIndex)
        }
    }
}

@Composable
private fun MarkdownTableRow(
    cells: List<String>,
    columnWidths: List<androidx.compose.ui.unit.Dp>,
    tableWidth: androidx.compose.ui.unit.Dp,
    color: Color,
    header: Boolean,
    rowIndex: Int,
) {
    Row(Modifier.width(tableWidth).height(IntrinsicSize.Min)) {
        columnWidths.forEachIndexed { index, width ->
            val cell = cells.getOrNull(index).orEmpty()
            Text(
                text = remember(cell) { markdownToAnnotatedString(cell) },
                color = color,
                fontWeight = if (header) FontWeight.SemiBold else FontWeight.Normal,
                fontSize = 13.sp,
                lineHeight = 18.sp,
                modifier = Modifier
                    .width(width)
                    .fillMaxHeight()
                    .background(
                        when {
                            header -> SuyuanColors.panel
                            rowIndex % 2 == 1 -> SuyuanColors.panel.copy(alpha = .42f)
                            else -> Color.White
                        }
                    )
                    .border(1.dp, SuyuanColors.border)
                    .padding(horizontal = 9.dp, vertical = 8.dp),
            )
        }
    }
}

private fun estimatedTableCellLength(value: String): Int = value.lineSequence()
    .map { line -> line.fold(0) { total, character -> total + if (character.code > 0xFF) 2 else 1 } }
    .maxOrNull()
    ?: 1

private fun parseMarkdownBlocks(content: String): List<MarkdownBlock> {
    val lines = content.lines()
    val blocks = mutableListOf<MarkdownBlock>()
    val text = StringBuilder()
    fun flushText() {
        if (text.isNotEmpty()) {
            blocks += MarkdownBlock.Text(text.toString().trim())
            text.clear()
        }
    }
    var index = 0
    while (index < lines.size) {
        val trimmed = lines[index].trim()
        MARKDOWN_IMAGE_LINE_RE.matchEntire(trimmed)?.let { match ->
            flushText()
            blocks += MarkdownBlock.Image(url = match.groupValues[2], alt = match.groupValues[1])
            index += 1
            continue
        }
        if (index + 1 < lines.size && isTableRow(lines[index]) && isTableDivider(lines[index + 1])) {
            flushText()
            val headers = splitTableRow(lines[index])
            val rows = mutableListOf<List<String>>()
            index += 2
            while (index < lines.size && isTableRow(lines[index])) {
                rows += splitTableRow(lines[index])
                index++
            }
            blocks += MarkdownBlock.Table(headers, rows)
        } else {
            text.append(lines[index]).append('\n')
            index++
        }
    }
    flushText()
    return blocks
}

private fun isTableRow(line: String): Boolean = line.contains('|') && splitTableRow(line).size >= 2

private fun isTableDivider(line: String): Boolean = line.trim().removePrefix("|").removeSuffix("|").split('|').all { cell -> cell.trim().matches(Regex(":?-{3,}:?")) }

private fun splitTableRow(line: String): List<String> = line.trim().removePrefix("|").removeSuffix("|").split('|').map { it.trim() }

@Composable
private fun AttachmentTray(state: AppUiState, viewModel: AppViewModel, context: android.content.Context) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(start = 4.dp, end = 4.dp, bottom = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        state.attachments.forEach { attachment ->
            val preview = state.attachmentPreviews[attachment.fileId]
            val isImage = isImageAttachment(attachment)
            var showViewer by remember(attachment.fileId) { mutableStateOf(false) }
            if (isImage) {
                LaunchedEffect(attachment.fileId) { viewModel.loadAttachmentPreview(attachment) }
                Box(
                    Modifier.size(66.dp).clip(RoundedCornerShape(10.dp))
                        .border(1.dp, SuyuanColors.border, RoundedCornerShape(10.dp))
                        .clickable(enabled = preview?.imageBytes != null) { showViewer = true },
                    contentAlignment = androidx.compose.ui.Alignment.Center,
                ) {
                    if (preview?.imageBytes != null) {
                        val bitmap = remember(preview.imageBytes) {
                            preview.imageBytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                        }
                        bitmap?.let {
                            androidx.compose.foundation.Image(
                                bitmap = it.asImageBitmap(), contentDescription = attachment.filename,
                                modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop,
                            )
                        }
                    } else {
                        CircularProgressIndicator(strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                    }
                    IconButton(
                        onClick = { viewModel.removeAttachment(attachment) },
                        modifier = Modifier
                            .align(androidx.compose.ui.Alignment.TopEnd)
                            .size(24.dp)
                            .clip(CircleShape)
                            .background(Color.Black.copy(alpha = .62f)),
                    ) {
                        Icon(painterResource(R.drawable.ic_close), contentDescription = "删除附件", tint = Color.White, modifier = Modifier.size(15.dp))
                    }
                }
            } else {
                Surface(
                    color = SuyuanColors.panel,
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.widthIn(min = 118.dp, max = 180.dp).height(58.dp),
                ) {
                    Row(
                        Modifier.padding(horizontal = 9.dp, vertical = 7.dp),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    ) {
                        Icon(painterResource(R.drawable.ic_file), contentDescription = attachment.filename, tint = SuyuanColors.primary, modifier = Modifier.size(25.dp))
                        Text(attachment.filename, color = SuyuanColors.text, fontSize = 11.sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.padding(start = 7.dp).weight(1f))
                        IconButton(onClick = { viewModel.removeAttachment(attachment) }, modifier = Modifier.size(28.dp)) {
                            Icon(painterResource(R.drawable.ic_close), contentDescription = "删除附件", tint = SuyuanColors.secondaryText, modifier = Modifier.size(16.dp))
                        }
                    }
                }
            }
            if (showViewer && preview?.imageBytes != null) {
                val bytes = preview.imageBytes
                val bitmap = remember(bytes) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
                bitmap?.let {
                    Dialog(onDismissRequest = { showViewer = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
                        Box(Modifier.fillMaxSize().background(Color.Black).clickable { showViewer = false }, contentAlignment = androidx.compose.ui.Alignment.Center) {
                            ZoomableBitmapPreview(
                                bitmap = it.asImageBitmap(),
                                contentDescription = attachment.filename,
                                backgroundColor = Color.Black,
                                contentScale = ContentScale.Fit,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
internal fun AttachmentView(attachment: UploadedAttachment, state: AppUiState, viewModel: AppViewModel, context: android.content.Context, inlineImage: Boolean = false) {
    val preview = state.attachmentPreviews[attachment.fileId]
    val isImage = isImageAttachment(attachment)
    if (isImage) {
        var showViewer by remember(attachment.fileId) { mutableStateOf(false) }
        LaunchedEffect(attachment.fileId) { viewModel.loadAttachmentPreview(attachment) }
        if (preview?.imageBytes != null) {
            val imageBytes = preview.imageBytes
            val bitmap = remember(imageBytes) { BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size) }
            val imageBitmap = bitmap?.asImageBitmap()
            if (imageBitmap != null) {
                androidx.compose.foundation.Image(
                    bitmap = imageBitmap, contentDescription = attachment.filename,
                    modifier = Modifier
                        .padding(top = 6.dp)
                        .then(if (inlineImage) Modifier.fillMaxWidth().aspectRatio(bitmap.width.toFloat() / bitmap.height.coerceAtLeast(1)) else Modifier.size(88.dp))
                        .clip(RoundedCornerShape(10.dp))
                        .clickable { showViewer = true },
                    contentScale = if (inlineImage) ContentScale.Fit else ContentScale.Crop,
                )
                if (showViewer) {
                    Dialog(onDismissRequest = { showViewer = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
                        androidx.compose.foundation.layout.Box(Modifier.fillMaxSize().background(Color.Black)) {
                            ZoomableBitmapPreview(
                                bitmap = imageBitmap,
                                contentDescription = attachment.filename,
                                backgroundColor = Color.Black,
                                contentScale = ContentScale.Fit,
                            )
                            IconButton(onClick = { showViewer = false }, modifier = Modifier.align(androidx.compose.ui.Alignment.TopEnd).statusBarsPadding().padding(8.dp)) {
                                Icon(painterResource(R.drawable.ic_close), contentDescription = "关闭图片预览", tint = Color.White)
                            }
                            TextButton(
                                onClick = {
                                    Toast.makeText(context, if (saveImageToGallery(context, imageBytes, attachment.filename)) "图片已保存" else "图片保存失败", Toast.LENGTH_SHORT).show()
                                },
                                modifier = Modifier.align(androidx.compose.ui.Alignment.BottomCenter).navigationBarsPadding().padding(bottom = 12.dp),
                            ) { Text("保存图片", color = Color.White) }
                        }
                    }
                }
            }
        } else if (preview?.error != null) {
            Text(preview.error, color = SuyuanColors.error, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
        } else {
            CircularProgressIndicator(strokeWidth = 2.dp, modifier = Modifier.size(18.dp).padding(top = 6.dp))
        }
        return
    }
    var showPreview by remember(attachment.fileId) { mutableStateOf(false) }
    LaunchedEffect(attachment.fileId, showPreview) { if (showPreview) viewModel.loadAttachmentPreview(attachment) }
    Row(
        Modifier
            .padding(top = 6.dp)
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Color.White)
            .border(1.dp, Color(0xFFE8EAED), RoundedCornerShape(12.dp))
            .clickable { showPreview = true }
            .padding(horizontal = 14.dp, vertical = 15.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        FileTypeBadge(attachment.filename, attachment.format)
        Column(Modifier.padding(start = 12.dp).weight(1f)) {
            Text(attachment.filename, color = SuyuanColors.text, fontSize = 15.sp, fontWeight = FontWeight.Medium, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            val formats = (listOf(attachment.format.ifBlank { attachment.filename.substringAfterLast('.', "文件") }) + attachment.variants.map { it.format }).distinct().joinToString(" · ") { it.uppercase() }
            Text("$formats · 点击查看", color = SuyuanColors.secondaryText, fontSize = 11.sp, modifier = Modifier.padding(top = 6.dp))
        }
        Icon(painterResource(R.drawable.ic_chevron_right), contentDescription = null, tint = Color(0xFFB8BDC4), modifier = Modifier.size(17.dp))
    }
    if (showPreview) {
        Dialog(onDismissRequest = { showPreview = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(Modifier.fillMaxSize(), color = SuyuanColors.background) {
                Column {
                    Row(
                        Modifier.fillMaxWidth().statusBarsPadding().height(56.dp).padding(horizontal = 8.dp),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    ) {
                        IconButton(onClick = { showPreview = false }) {
                            Icon(painterResource(R.drawable.ic_close), contentDescription = "关闭预览", tint = SuyuanColors.text)
                        }
                        Text("预览", color = SuyuanColors.text, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
                        val pdfBytes = preview?.pdfBytes
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                            if (pdfBytes != null && !attachment.filename.endsWith(".pdf", true) && attachment.variants.none { it.format.equals("pdf", true) }) {
                                TextButton(onClick = {
                                    viewModel.downloadPreview(context, attachment, pdfBytes) { success ->
                                        Toast.makeText(context, if (success) "PDF 已保存到下载/许昌环境Agent" else "下载失败", Toast.LENGTH_SHORT).show()
                                    }
                                }) { Text("下载 PDF") }
                            }
                            TextButton(onClick = {
                                viewModel.downloadAttachment(context, attachment) { success ->
                                    Toast.makeText(context, if (success) "文件已保存到下载/许昌环境Agent" else "下载失败", Toast.LENGTH_SHORT).show()
                                }
                            }) { Text("下载 ${attachment.filename.substringAfterLast('.', "文件").uppercase()}") }
                            attachment.variants.forEach { variant ->
                                val label = when (variant.format.lowercase()) {
                                    "doc", "docx" -> "下载 Word"
                                    "xls", "xlsx" -> "下载 Excel"
                                    "pdf" -> "下载 PDF"
                                    "html", "htm" -> "下载 HTML"
                                    else -> "下载 ${variant.format.uppercase()}"
                                }
                                TextButton(onClick = {
                                    viewModel.downloadAttachment(context, attachment.copy(filename = variant.filename, mimeType = variant.mimeType, url = variant.url, downloadUrl = variant.url, previewUrl = null)) { success ->
                                        Toast.makeText(context, if (success) "${label}成功" else "下载失败", Toast.LENGTH_SHORT).show()
                                    }
                                }) { Text(label) }
                            }
                        }
                    }
                    when {
                        preview?.loading == true -> Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) { CircularProgressIndicator() }
                        preview?.error != null -> Text(preview.error, color = SuyuanColors.error, modifier = Modifier.padding(24.dp))
                        else -> DocumentPreviewContent(attachment, preview?.pdfBytes, preview?.text, viewModel, context, showDownload = false)
                    }
                }
            }
        }
    }
}

@Composable
private fun FileTypeBadge(filename: String, format: String = "") {
    val ext = format.ifBlank { filename.substringAfterLast('.', "file") }.uppercase().take(4)
    val tint = when (ext) {
        "PDF" -> Color(0xFFE74C3C)
        "DOC", "DOCX" -> Color(0xFF2478D4)
        "XLS", "XLSX", "CSV" -> Color(0xFF1E9B62)
        "PPT", "PPTX" -> Color(0xFFE67E22)
        else -> SuyuanColors.primary
    }
    Surface(color = tint, shape = RoundedCornerShape(6.dp), modifier = Modifier.size(width = 44.dp, height = 52.dp)) {
        Box(contentAlignment = androidx.compose.ui.Alignment.Center) {
            Text(ext, color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun DocumentPreviewContent(
    attachment: UploadedAttachment,
    pdfBytes: ByteArray?,
    text: String?,
    viewModel: AppViewModel,
    context: android.content.Context,
    showDownload: Boolean = true,
) {
    Column(Modifier.fillMaxSize()) {
        if (pdfBytes != null) {
            PdfDocumentPreview(pdfBytes, attachment.filename, context)
        } else if (attachment.mimeType.equals("text/html", ignoreCase = true) || attachment.filename.endsWith(".html", true) || attachment.filename.endsWith(".htm", true)) {
            AndroidView(
                factory = {
                    android.webkit.WebView(it).apply {
                        settings.javaScriptEnabled = false
                        settings.allowFileAccess = false
                        settings.setSupportZoom(true)
                        settings.builtInZoomControls = true
                        settings.displayZoomControls = false
                        settings.loadWithOverviewMode = true
                        settings.useWideViewPort = true
                    }
                },
                update = { it.loadDataWithBaseURL(null, text.orEmpty(), "text/html", "UTF-8", null) },
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
        } else if (!text.isNullOrBlank()) {
            val isMarkdown = attachment.filename.endsWith(".md", true) || attachment.filename.endsWith(".markdown", true)
            if (isMarkdown) {
                Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 8.dp, vertical = 6.dp)) {
                    MarkdownContent(text, SuyuanColors.text)
                }
            } else {
                Text(text, color = SuyuanColors.text, fontSize = 13.sp, lineHeight = 20.sp, fontFamily = if (attachment.mimeType.contains("json") || attachment.filename.endsWith(".csv", true)) FontFamily.Monospace else FontFamily.Default, modifier = Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 8.dp, vertical = 6.dp))
            }
        } else {
            Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = androidx.compose.ui.Alignment.Center) {
                Text("暂无可用预览", color = SuyuanColors.secondaryText, fontSize = 12.sp)
            }
        }
        if (showDownload) {
            TextButton(onClick = {
                viewModel.downloadAttachment(context, attachment) { success ->
                    Toast.makeText(context, if (success) "已保存到下载/许昌环境Agent" else "下载失败", Toast.LENGTH_SHORT).show()
                }
            }, modifier = Modifier.align(androidx.compose.ui.Alignment.End)) {
                Text("下载")
            }
        }
    }
}

@Composable
private fun PdfDocumentPreview(bytes: ByteArray, filename: String, context: android.content.Context) {
    val combinedBitmap by produceState<Bitmap?>(initialValue = null, key1 = bytes) {
        value = withContext(Dispatchers.Default) { renderPdfLongImage(context, bytes) }
    }
    if (combinedBitmap == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
            Column(horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
                CircularProgressIndicator(color = SuyuanColors.primary, strokeWidth = 2.dp)
                Text("正在生成 PDF 预览…", color = SuyuanColors.secondaryText, fontSize = 12.sp, modifier = Modifier.padding(top = 10.dp))
            }
        }
    } else {
        PdfLongImagePreview(combinedBitmap!!, filename)
    }
}

@Composable
private fun ZoomableBitmapPreview(
    bitmap: ImageBitmap,
    contentDescription: String,
    backgroundColor: Color = Color.White,
    contentScale: ContentScale = ContentScale.FillWidth,
) {
    var scale by remember(bitmap) { mutableFloatStateOf(1.08f) }
    var offset by remember(bitmap) { mutableStateOf(Offset.Zero) }
    var viewport by remember(bitmap) { mutableStateOf(IntSize.Zero) }

    fun bounded(value: Offset, targetScale: Float): Offset {
        val maxX = (viewport.width * (targetScale - 1f) / 2f + 48f).coerceAtLeast(48f)
        val maxY = (viewport.height * (targetScale - 1f) / 2f + 48f).coerceAtLeast(48f)
        return Offset(value.x.coerceIn(-maxX, maxX), value.y.coerceIn(-maxY, maxY))
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(backgroundColor)
            .onSizeChanged { viewport = it }
            .pointerInput(bitmap) {
                detectTransformGestures { centroid, pan, zoom, _ ->
                    val previousScale = scale
                    val nextScale = (scale * zoom).coerceIn(1f, 4f)
                    val scaleChange = nextScale / previousScale
                    val center = Offset(viewport.width / 2f, viewport.height / 2f)
                    val nextOffset = offset + pan + (centroid - center) * (1f - scaleChange)
                    scale = nextScale
                    offset = bounded(nextOffset, nextScale)
                }
            },
        contentAlignment = androidx.compose.ui.Alignment.Center,
    ) {
        androidx.compose.foundation.Image(
            bitmap = bitmap,
            contentDescription = contentDescription,
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer {
                    scaleX = scale
                    scaleY = scale
                    translationX = offset.x
                    translationY = offset.y
                },
            contentScale = contentScale,
        )
    }
}

private fun renderPdfLongImage(context: android.content.Context, bytes: ByteArray): Bitmap? {
    val file = runCatching {
        File.createTempFile("preview-", ".pdf", context.cacheDir).apply { writeBytes(bytes) }
    }.getOrNull() ?: return null
    return runCatching {
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
            android.graphics.pdf.PdfRenderer(descriptor).use { renderer ->
                if (renderer.pageCount == 0) return@use null
                val targetWidth = 900
                val pageSizes = (0 until renderer.pageCount).map { index ->
                    renderer.openPage(index).use { page ->
                        val scale = minOf(2f, targetWidth.toFloat() / page.width.toFloat())
                        Pair((page.width * scale).toInt(), (page.height * scale).toInt())
                    }
                }
                val width = pageSizes.maxOf { it.first }
                val totalHeight = pageSizes.sumOf { it.second.toLong() }
                // Android bitmaps have a practical maximum dimension; reduce
                // the scale for unusually long PDFs before allocating the canvas.
                val heightLimit = 30000L
                val reduction = if (totalHeight > heightLimit) heightLimit.toDouble() / totalHeight else 1.0
                val finalWidth = (width * reduction).toInt().coerceAtLeast(1)
                val finalHeight = (totalHeight * reduction).toInt().coerceAtLeast(1)
                val bitmap = Bitmap.createBitmap(finalWidth, finalHeight, Bitmap.Config.ARGB_8888)
                bitmap.eraseColor(AndroidColor.WHITE)
                val canvas = Canvas(bitmap)
                var top = 0f
                (0 until renderer.pageCount).forEachIndexed { index, _ ->
                    renderer.openPage(index).use { page ->
                        val pageWidth = (pageSizes[index].first * reduction).toInt().coerceAtLeast(1)
                        val pageHeight = (pageSizes[index].second * reduction).toInt().coerceAtLeast(1)
                        val pageBitmap = Bitmap.createBitmap(pageWidth, pageHeight, Bitmap.Config.ARGB_8888)
                        pageBitmap.eraseColor(AndroidColor.WHITE)
                        page.render(pageBitmap, null, null, android.graphics.pdf.PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        canvas.drawBitmap(pageBitmap, ((finalWidth - pageWidth) / 2f), top, null)
                        pageBitmap.recycle()
                        top += pageHeight
                    }
                }
                bitmap
            }
        }
    }.getOrNull().also { file.delete() }
}

@Composable
private fun PdfLongImagePreview(bitmap: Bitmap, filename: String) {
    var scale by remember(bitmap) { mutableFloatStateOf(1f) }
    var offset by remember(bitmap) { mutableStateOf(Offset.Zero) }
    val scrollState = rememberScrollState()
    Column(
        Modifier.fillMaxSize().verticalScroll(scrollState, enabled = scale <= 1.01f),
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
    ) {
        androidx.compose.foundation.Image(
            bitmap = bitmap.asImageBitmap(),
            contentDescription = filename,
            contentScale = ContentScale.FillWidth,
            modifier = Modifier
                .fillMaxWidth()
                .graphicsLayer {
                    scaleX = scale
                    scaleY = scale
                    translationX = offset.x
                    translationY = offset.y
                }
                .pointerInput(bitmap) {
                    awaitEachGesture {
                        awaitFirstDown(requireUnconsumed = false)
                        while (true) {
                            val event = awaitPointerEvent()
                            if (event.changes.none { it.pressed }) break
                            // Leave one-finger movement unconsumed so the
                            // parent verticalScroll can page through the PDF.
                            if (event.changes.count { it.pressed } >= 2) {
                                val nextScale = (scale * event.calculateZoom()).coerceIn(1f, 4f)
                                scale = nextScale
                                offset += event.calculatePan()
                                if (scale <= 1.01f) offset = Offset.Zero
                                event.changes.forEach { it.consume() }
                            }
                        }
                    }
                },
        )
    }
}

private fun saveImageToGallery(context: android.content.Context, bytes: ByteArray, filename: String): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false
    val values = ContentValues().apply {
        put(MediaStore.Images.Media.DISPLAY_NAME, filename.substringBeforeLast('.') + ".jpg")
        put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
        put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/许昌环境Agent")
    }
    val resolver = context.contentResolver
    val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return false
    return runCatching { resolver.openOutputStream(uri)?.use { it.write(bytes) }; true }
        .getOrElse { resolver.delete(uri, null, null); false }
}

internal object SuyuanColors {
    val primary = Color(0xFF007AFF)
    val background = Color.White
    val panel = Color(0xFFF7F7F9)
    val text = Color(0xFF111111)
    val controlIcon = Color(0xFF3C3C43)
    val secondaryText = Color(0xFF8E8E93)
    val border = Color(0xFFD2D2D7)
    val error = Color(0xFFFF3B30)
}

private fun markdownToAnnotatedString(markdown: String): AnnotatedString = buildAnnotatedString {
    markdown.lines().forEachIndexed { index, line ->
        val heading = line.trimStart().startsWith("#")
        if (heading) withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(line.trimStart().trimStart('#').trim()) }
        else appendInlineMarkdown(line)
        if (index < markdown.lines().lastIndex) append('\n')
    }
}

private fun AnnotatedString.Builder.appendInlineMarkdown(line: String) {
    val pattern = Regex("(\\*\\*[^*]+\\*\\*|`[^`]+`)")
    var cursor = 0
    pattern.findAll(line).forEach { match ->
        append(line.substring(cursor, match.range.first))
        val value = match.value
        when {
            value.startsWith("**") -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(value.removeSurrounding("**")) }
            value.startsWith("`") -> withStyle(SpanStyle(fontFamily = FontFamily.Monospace)) { append(value.removeSurrounding("`")) }
        }
        cursor = match.range.last + 1
    }
    append(line.substring(cursor))
}


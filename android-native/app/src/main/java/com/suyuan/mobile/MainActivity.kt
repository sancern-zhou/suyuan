package com.suyuan.mobile

import android.Manifest
import android.content.ContentValues
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.graphics.Bitmap
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
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.BasicTextField
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
import androidx.compose.ui.graphics.Color
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
import androidx.compose.ui.layout.ContentScale
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
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlin.math.roundToInt

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        window.statusBarColor = android.graphics.Color.BLACK
        window.navigationBarColor = android.graphics.Color.BLACK
        setContent {
            val context = LocalContext.current
            val appViewModel: AppViewModel = viewModel(
                factory = AppViewModelFactory(SocialAppRepository(SocialAppApi()), AppSessionStore(context))
            )
            SuyuanApp(appViewModel)
        }
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
private fun SuyuanApp(viewModel: AppViewModel) {
    val state by viewModel.state.collectAsState()
    Surface(modifier = Modifier.fillMaxSize(), color = SuyuanColors.background) {
        if (state.loggedIn) ChatScreen(state, viewModel) else LoginScreen(state, viewModel)
    }
}

@Composable
private fun LoginScreen(state: AppUiState, viewModel: AppViewModel) {
    var accountId by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    Column(
        Modifier.fillMaxSize().background(SuyuanColors.background).padding(horizontal = 28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
    ) {
        androidx.compose.foundation.Image(
            painter = painterResource(com.suyuan.mobile.R.mipmap.ic_launcher),
            contentDescription = "溯源 Agent",
            modifier = Modifier.size(88.dp).clip(RoundedCornerShape(22.dp)),
            contentScale = ContentScale.Crop,
        )
        Text("溯源 Agent", color = SuyuanColors.text, fontSize = 26.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 18.dp))
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
        AppTopBar(showHistory = showHistory, onHistory = { showHistory = true }, onBack = { showHistory = false }, onNew = { showHistory = false; viewModel.newConversation() })
        if (showHistory) {
            HistoryPanel(state, viewModel, onBack = { showHistory = false })
        } else Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
            val conversationListState = rememberLazyListState()
            val waitingForAssistant = state.loading && state.messages.lastOrNull()?.kind == "user"
            var initiallyScrolledSession by remember { mutableStateOf<String?>(null) }
            LaunchedEffect(state.messages.size, state.messages.lastOrNull()?.content?.length, state.messages.lastOrNull()?.kind, waitingForAssistant) {
                if (state.messages.isNotEmpty()) {
                    val lastIndex = state.messages.lastIndex
                    val visibleLast = conversationListState.layoutInfo.visibleItemsInfo.lastOrNull()?.index
                    val lastMessageIsNewUserInput = state.messages.lastOrNull()?.kind == "user"
                    val targetIndex = lastIndex + if (waitingForAssistant) 1 else 0
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
                    item { EmptyChatState(loading = state.loading) }
                } else items(state.messages, key = { it.id }) {
                    ChatMessageView(it, state, viewModel)
                }
                if (waitingForAssistant) {
                    item(key = "thinking-indicator") { ThinkingIndicator() }
                }
            }
        val canCancel = state.loading && state.sessionId != null
        if (state.attachments.isNotEmpty()) {
            AttachmentTray(state, viewModel, context)
        }
        Surface(
            color = Color.White,
            shape = RoundedCornerShape(22.dp),
            tonalElevation = 1.dp,
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp).imePadding().navigationBarsPadding(),
        ) {
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
                            .border(1.5.dp, if (recording) SuyuanColors.error else SuyuanColors.secondaryText, CircleShape)
                            .pointerInteropFilter { handleVoiceEvent(it, toggleOnTap = true) },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(
                            painterResource(R.drawable.ic_voice_right),
                            contentDescription = if (recording) "松开停止" else "按住切换语音输入",
                            tint = if (recording) SuyuanColors.error else SuyuanColors.secondaryText,
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
                            .border(1.5.dp, SuyuanColors.secondaryText, CircleShape)
                            .clickable { picker.launch("*/*") },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(painterResource(R.drawable.ic_plus), contentDescription = "添加附件", tint = SuyuanColors.secondaryText, modifier = Modifier.size(16.dp))
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
                            Icon(painterResource(if (hasDraft) R.drawable.ic_arrow_up else R.drawable.ic_stop), contentDescription = if (hasDraft) "发送" else "取消生成", tint = Color.White, modifier = Modifier.size(16.dp))
                        }
                    }
                } else {
                    Box(
                        Modifier.size(30.dp).clip(CircleShape)
                            .border(1.5.dp, SuyuanColors.secondaryText, CircleShape)
                            .clickable(enabled = !recording) { voiceMode = false },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(painterResource(R.drawable.ic_keyboard), contentDescription = "切换键盘输入", tint = SuyuanColors.secondaryText, modifier = Modifier.size(16.dp))
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
                            .border(1.5.dp, SuyuanColors.secondaryText, CircleShape)
                            .clickable { picker.launch("*/*") },
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(painterResource(R.drawable.ic_plus), contentDescription = "添加附件", tint = SuyuanColors.secondaryText, modifier = Modifier.size(16.dp))
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
private fun AppTopBar(showHistory: Boolean, onHistory: () -> Unit, onBack: () -> Unit, onNew: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(Color.White).statusBarsPadding().padding(horizontal = 18.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
            IconButton(onClick = if (showHistory) onBack else onHistory) {
                Icon(painterResource(if (showHistory) R.drawable.ic_back else R.drawable.ic_menu), contentDescription = if (showHistory) "返回对话" else "历史会话", tint = SuyuanColors.text)
            }
            if (showHistory) Text("历史会话", color = SuyuanColors.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp))
        }
        IconButton(onClick = onNew) {
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
    if (state.sessions.isEmpty()) {
        Column(Modifier.fillMaxSize(), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Text("暂无历史会话", color = SuyuanColors.secondaryText, fontSize = 16.sp)
        }
        return
    }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 12.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
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
                        Text(session.sessionId, color = SuyuanColors.secondaryText, fontSize = 11.sp, maxLines = 1)
                    }
                    Text(if (session.sessionId == state.sessionId) "当前" else "", color = SuyuanColors.primary, fontSize = 12.sp)
                    IconButton(onClick = { actionSession = session }) {
                        Icon(painterResource(R.drawable.ic_more), contentDescription = "会话操作", tint = SuyuanColors.secondaryText)
                    }
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
private fun EmptyChatState(loading: Boolean = false) {
    Column(Modifier.fillMaxWidth().padding(top = 110.dp), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
        Text(if (loading) "正在恢复会话" else "开始对话", color = SuyuanColors.text, fontSize = 22.sp, fontWeight = FontWeight.Medium)
        Text(
            if (loading) "正在加载最近的会话内容…" else "向溯源 Agent 描述你想完成的任务",
            color = SuyuanColors.secondaryText,
            fontSize = 13.sp,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
}

@Composable
private fun ThinkingIndicator() {
    Row(
        Modifier.fillMaxWidth().padding(start = 8.dp, top = 2.dp, bottom = 6.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        CircularProgressIndicator(
            color = SuyuanColors.secondaryText,
            strokeWidth = 2.dp,
            modifier = Modifier.size(15.dp),
        )
        Text(
            "正在思考…",
            color = SuyuanColors.secondaryText,
            fontSize = 13.sp,
            modifier = Modifier.padding(start = 7.dp),
        )
    }
}

@Composable
private fun ChatMessageView(message: ChatMessage, state: AppUiState, viewModel: AppViewModel) {
    val context = LocalContext.current
    val isUser = message.kind == "user"
    val horizontal = if (isUser) Arrangement.End else Arrangement.Start
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = horizontal) {
        val bubbleShape = RoundedCornerShape(18.dp)
        val messageModifier = Modifier
            .widthIn(max = if (isUser) 330.dp else 390.dp)
            .then(
                if (isUser) {
                    Modifier
                        .clip(bubbleShape)
                        .background(Color.Transparent)
                        .border(1.dp, SuyuanColors.primary.copy(alpha = .42f), bubbleShape)
                } else Modifier
            )
            .padding(horizontal = 14.dp, vertical = 7.dp)
        Column(messageModifier) {
            when (message.kind) {
                "thought" -> {
                    Row(
                        modifier = Modifier.fillMaxWidth().clickable { viewModel.toggleThought(message.id) },
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    ) {
                        Icon(painterResource(if (message.expanded) R.drawable.ic_chevron_down else R.drawable.ic_chevron_right), contentDescription = "展开或收起思考", tint = SuyuanColors.secondaryText, modifier = Modifier.size(18.dp))
                        Text("思考过程", color = SuyuanColors.secondaryText, fontSize = 13.sp, modifier = Modifier.padding(start = 4.dp))
                        if (message.streaming) Text("…", color = SuyuanColors.secondaryText, fontSize = 16.sp)
                    }
                    if (message.expanded) {
                        Text(message.content, color = SuyuanColors.secondaryText, fontSize = 13.sp, lineHeight = 19.sp, modifier = Modifier.padding(start = 22.dp, top = 4.dp))
                    }
                }
                "tool" -> {
                    Text(message.content, color = SuyuanColors.secondaryText, fontSize = 12.sp)
                    message.attachments.forEach { attachment -> AttachmentView(attachment, state, viewModel, context) }
                }
                "error" -> Text(message.content, color = SuyuanColors.error, fontSize = 13.sp, lineHeight = 19.sp)
                else -> {
                    if (message.content.isNotBlank()) {
                        MarkdownContent(message.content, if (isUser) SuyuanColors.primary else SuyuanColors.text)
                    }
                    if (message.streaming) {
                        // Keep a lightweight cursor beside the partial answer so users
                        // can tell that the response is still arriving.
                        Text("|", color = SuyuanColors.primary, fontSize = 15.sp)
                    }
                    val visibleAttachments = if (message.attachments.any(::isImageAttachment)) {
                        message.attachments.filterNot { it.mimeType.equals("application/json", ignoreCase = true) && !isImageAttachment(it) }
                    } else message.attachments
                    visibleAttachments.forEach { attachment ->
                        AttachmentView(attachment, state, viewModel, context)
                    }
                }
            }
        }
    }
}

private sealed class MarkdownBlock {
    data class Text(val value: String) : MarkdownBlock()
    data class Table(val headers: List<String>, val rows: List<List<String>>) : MarkdownBlock()
}

@Composable
private fun MarkdownContent(content: String, color: Color) {
    parseMarkdownBlocks(content).forEach { block ->
        when (block) {
            is MarkdownBlock.Text -> if (block.value.isNotBlank()) {
                Text(remember(block.value) { markdownToAnnotatedString(block.value) }, color = color, fontSize = 15.sp, lineHeight = 22.sp)
            }
            is MarkdownBlock.Table -> MarkdownTable(block.headers, block.rows, color)
        }
    }
}

@Composable
private fun MarkdownTable(headers: List<String>, rows: List<List<String>>, color: Color) {
    Column(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 6.dp)) {
        Row {
            headers.forEach { cell ->
                Text(cell, color = color, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, modifier = Modifier.widthIn(min = 100.dp, max = 180.dp).border(1.dp, SuyuanColors.border).padding(7.dp))
            }
        }
        rows.forEachIndexed { rowIndex, row ->
            Row {
                headers.indices.forEach { index ->
                    Text(row.getOrNull(index).orEmpty(), color = color, fontSize = 13.sp, modifier = Modifier.widthIn(min = 100.dp, max = 180.dp).border(1.dp, SuyuanColors.border).padding(7.dp))
                }
            }
        }
    }
}

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

private fun isTableRow(line: String): Boolean = line.count { it == '|' } >= 2

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
                    }
                }
            }
            if (showViewer && preview?.imageBytes != null) {
                val bytes = preview.imageBytes
                val bitmap = remember(bytes) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
                bitmap?.let {
                    Dialog(onDismissRequest = { showViewer = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
                        Box(Modifier.fillMaxSize().background(Color.Black).clickable { showViewer = false }, contentAlignment = androidx.compose.ui.Alignment.Center) {
                            androidx.compose.foundation.Image(bitmap = it.asImageBitmap(), contentDescription = attachment.filename, modifier = Modifier.fillMaxWidth().padding(18.dp), contentScale = ContentScale.Fit)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AttachmentView(attachment: UploadedAttachment, state: AppUiState, viewModel: AppViewModel, context: android.content.Context) {
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
                        .size(88.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .clickable { showViewer = true },
                    contentScale = ContentScale.Crop,
                )
                if (showViewer) {
                    Dialog(onDismissRequest = { showViewer = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
                        androidx.compose.foundation.layout.Box(Modifier.fillMaxSize().background(Color.Black)) {
                            androidx.compose.foundation.Image(
                                bitmap = imageBitmap, contentDescription = attachment.filename,
                                modifier = Modifier.fillMaxSize().padding(18.dp).pointerInput(imageBytes) {
                                    detectTapGestures(onLongPress = {
                                        Toast.makeText(context, if (saveImageToGallery(context, imageBytes, attachment.filename)) "图片已保存" else "图片保存失败", Toast.LENGTH_SHORT).show()
                                    })
                                }, contentScale = ContentScale.Fit,
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
    LaunchedEffect(attachment.fileId) { viewModel.loadAttachmentPreview(attachment) }
    Row(
        Modifier
            .padding(top = 6.dp)
            .widthIn(min = 210.dp, max = 280.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(SuyuanColors.panel)
            .clickable { showPreview = true }
            .padding(horizontal = 9.dp, vertical = 7.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        FileTypeBadge(attachment.filename)
        Text(attachment.filename, color = SuyuanColors.text, fontSize = 12.sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.padding(start = 9.dp).weight(1f))
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
                                        Toast.makeText(context, if (success) "PDF 已保存到下载/溯源Agent" else "下载失败", Toast.LENGTH_SHORT).show()
                                    }
                                }) { Text("下载 PDF") }
                            }
                            TextButton(onClick = {
                                viewModel.downloadAttachment(context, attachment) { success ->
                                    Toast.makeText(context, if (success) "文件已保存到下载/溯源Agent" else "下载失败", Toast.LENGTH_SHORT).show()
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
private fun FileTypeBadge(filename: String) {
    val ext = filename.substringAfterLast('.', "file").uppercase().take(4)
    val tint = when (ext) {
        "PDF" -> Color(0xFFE74C3C)
        "DOC", "DOCX" -> Color(0xFF2478D4)
        "XLS", "XLSX", "CSV" -> Color(0xFF1E9B62)
        "PPT", "PPTX" -> Color(0xFFE67E22)
        else -> SuyuanColors.primary
    }
    Surface(color = tint, shape = RoundedCornerShape(5.dp), modifier = Modifier.size(42.dp)) {
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
    Column(Modifier.padding(start = 29.dp, top = 6.dp, end = 4.dp)) {
        if (pdfBytes != null) {
            val bitmap = remember(pdfBytes) { renderPdfFirstPage(context, pdfBytes)?.asImageBitmap() }
            if (bitmap != null) {
                androidx.compose.foundation.Image(
                    bitmap = bitmap,
                    contentDescription = attachment.filename,
                    modifier = Modifier.fillMaxWidth().heightIn(max = 360.dp).clip(RoundedCornerShape(8.dp)),
                    contentScale = ContentScale.Fit,
                )
            } else {
                Text("暂时无法渲染此文档", color = SuyuanColors.secondaryText, fontSize = 12.sp)
            }
        } else if (attachment.mimeType.equals("text/html", ignoreCase = true) || attachment.filename.endsWith(".html", true) || attachment.filename.endsWith(".htm", true)) {
            AndroidView(
                factory = { android.webkit.WebView(it).apply { settings.javaScriptEnabled = false; settings.allowFileAccess = false } },
                update = { it.loadDataWithBaseURL(null, text.orEmpty(), "text/html", "UTF-8", null) },
                modifier = Modifier.fillMaxWidth().heightIn(min = 80.dp, max = 300.dp),
            )
        } else if (!text.isNullOrBlank()) {
            val isMarkdown = attachment.filename.endsWith(".md", true) || attachment.filename.endsWith(".markdown", true)
            if (isMarkdown) {
                Column(Modifier.heightIn(max = 300.dp).verticalScroll(rememberScrollState())) {
                    MarkdownContent(text, SuyuanColors.text)
                }
            } else {
                Text(text, color = SuyuanColors.text, fontSize = 12.sp, lineHeight = 18.sp, fontFamily = if (attachment.mimeType.contains("json") || attachment.filename.endsWith(".csv", true)) FontFamily.Monospace else FontFamily.Default, modifier = Modifier.heightIn(max = 300.dp).verticalScroll(rememberScrollState()))
            }
        } else {
            Text("暂无可用预览", color = SuyuanColors.secondaryText, fontSize = 12.sp)
        }
        if (showDownload) {
            TextButton(onClick = {
                viewModel.downloadAttachment(context, attachment) { success ->
                    Toast.makeText(context, if (success) "已保存到下载/溯源Agent" else "下载失败", Toast.LENGTH_SHORT).show()
                }
            }, modifier = Modifier.align(androidx.compose.ui.Alignment.End)) {
                Text("下载")
            }
        }
    }
}

private fun renderPdfFirstPage(context: android.content.Context, bytes: ByteArray): Bitmap? {
    val file = runCatching {
        File.createTempFile("preview-", ".pdf", context.cacheDir).apply { writeBytes(bytes) }
    }.getOrNull() ?: return null
    return runCatching {
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
            android.graphics.pdf.PdfRenderer(descriptor).use { renderer ->
                if (renderer.pageCount == 0) {
                    null
                } else {
                    renderer.openPage(0).use { page ->
                        val scale = minOf(2f, 900f / page.width.toFloat())
                        val bitmap = Bitmap.createBitmap((page.width * scale).toInt(), (page.height * scale).toInt(), Bitmap.Config.ARGB_8888)
                        bitmap.eraseColor(AndroidColor.WHITE)
                        page.render(bitmap, null, null, android.graphics.pdf.PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        bitmap
                    }
                }
            }
        }
    }.getOrNull().also { file.delete() }
}

private fun saveImageToGallery(context: android.content.Context, bytes: ByteArray, filename: String): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false
    val values = ContentValues().apply {
        put(MediaStore.Images.Media.DISPLAY_NAME, filename.substringBeforeLast('.') + ".jpg")
        put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
        put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/溯源Agent")
    }
    val resolver = context.contentResolver
    val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return false
    return runCatching { resolver.openOutputStream(uri)?.use { it.write(bytes) }; true }
        .getOrElse { resolver.delete(uri, null, null); false }
}

private object SuyuanColors {
    val primary = Color(0xFF007AFF)
    val background = Color.White
    val panel = Color(0xFFF7F7F9)
    val text = Color(0xFF111111)
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

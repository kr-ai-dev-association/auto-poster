package com.autoposter.app.ui.pipeline

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.autoposter.app.ui.pipeline.components.*
import com.autoposter.app.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PipelineScreen(
    viewModel: PipelineViewModel,
    onLogout: () -> Unit
) {
    val config by viewModel.config.collectAsStateWithLifecycle()
    val pipelineState by viewModel.pipelineState.collectAsStateWithLifecycle()
    val categories by viewModel.categories.collectAsStateWithLifecycle()
    val history by viewModel.history.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        "Auto Poster",
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary
                    )
                },
                actions = {
                    IconButton(onClick = onLogout) {
                        Icon(
                            Icons.AutoMirrored.Filled.Logout,
                            contentDescription = "로그아웃",
                            tint = TextSecondary
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = DarkBackground
                )
            )
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Configuration section
            ConfigSection(
                config = config,
                categories = categories,
                languages = viewModel.languages,
                voices = viewModel.voices,
                slideCountOptions = viewModel.slideCountOptions,
                isRunning = pipelineState.isRunning,
                onTopicChange = viewModel::setTopic,
                onInstructionsChange = viewModel::setAdditionalInstructions,
                onCategoryChange = viewModel::setCategory,
                onSlideCountChange = viewModel::setSlideCount,
                onLanguageChange = viewModel::setLanguage,
                onVoiceChange = viewModel::setVoice,
                onPrivacyChange = viewModel::setYoutubePrivacy,
                onStartPipeline = viewModel::startPipeline
            )

            // Progress section
            ProgressSection(
                state = pipelineState,
                steps = viewModel.steps,
                onCancel = viewModel::cancelPipeline
            )

            // Completion card
            if (pipelineState.status == "completed" && pipelineState.result != null) {
                CompletionCard(result = pipelineState.result!!)
            }

            // Error card
            if (pipelineState.status == "failed" && pipelineState.error != null) {
                ErrorCard(
                    error = pipelineState.error!!,
                    onRetry = viewModel::resetPipeline
                )
            }

            // History
            HistorySection(history = history)

            Spacer(Modifier.height(16.dp))
        }
    }
}

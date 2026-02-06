package com.autoposter.app.ui.pipeline

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.autoposter.app.data.local.TokenManager
import com.autoposter.app.data.remote.api.ConfigApi
import com.autoposter.app.data.repository.PipelineRepository
import com.autoposter.app.domain.model.*
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ConfigState(
    val topic: String = "",
    val additionalInstructions: String = "",
    val category: String = "tech",
    val slideCount: Int = 15,
    val language: String = "ko",
    val voice: String = "Leda",
    val youtubePrivacy: String = "private"
)

@HiltViewModel
class PipelineViewModel @Inject constructor(
    private val pipelineRepository: PipelineRepository,
    private val configApi: ConfigApi,
    private val tokenManager: TokenManager
) : ViewModel() {

    private val _config = MutableStateFlow(ConfigState())
    val config: StateFlow<ConfigState> = _config.asStateFlow()

    private val _pipelineState = MutableStateFlow(PipelineUiState())
    val pipelineState: StateFlow<PipelineUiState> = _pipelineState.asStateFlow()

    private val _categories = MutableStateFlow<List<Category>>(emptyList())
    val categories: StateFlow<List<Category>> = _categories.asStateFlow()

    private val _history = MutableStateFlow<List<PipelineHistoryItem>>(emptyList())
    val history: StateFlow<List<PipelineHistoryItem>> = _history.asStateFlow()

    val steps = PipelineStepId.values().toList()
    val voices = VoiceData.voices
    val languages = LanguageData.languages
    val slideCountOptions = listOf(10, 12, 15, 18, 20)

    private var pollingJob: Job? = null

    init {
        loadCategories()
        loadHistory()
        restoreRunningPipeline()
    }

    private fun loadCategories() {
        viewModelScope.launch {
            try {
                val response = configApi.getCategories()
                _categories.value = response.categories.map {
                    Category(id = it.id, nameKo = it.nameKo, nameEn = it.nameEn)
                }
            } catch (_: Exception) {
                // Use default if API fails
                _categories.value = listOf(
                    Category("tech", "테크", "Tech"),
                    Category("educational", "교육", "Educational"),
                    Category("entertainment", "엔터테인먼트", "Entertainment"),
                )
            }
        }
    }

    private fun loadHistory() {
        viewModelScope.launch {
            pipelineRepository.listPipelines().onSuccess { pipelines ->
                _history.value = pipelines
                    .sortedByDescending { it.startedAt }
                    .take(5)
                    .map { pipeline ->
                        PipelineHistoryItem(
                            id = pipeline.id,
                            topic = pipeline.topic,
                            status = pipeline.status,
                            title = pipeline.result?.title,
                            youtubeUrl = pipeline.result?.youtube?.url
                        )
                    }
            }
        }
    }

    private fun restoreRunningPipeline() {
        viewModelScope.launch {
            val savedId = pipelineRepository.getSavedPipelineId() ?: return@launch
            pipelineRepository.getPipelineStatus(savedId).onSuccess { pipeline ->
                if (pipeline.status == "running" || pipeline.status == "starting") {
                    _config.update { it.copy(topic = pipeline.topic ?: "") }
                    _pipelineState.update {
                        PipelineUiState(
                            isRunning = true,
                            pipelineId = savedId,
                            status = "running",
                            progress = pipeline.progress,
                            message = pipeline.message ?: "파이프라인 복원 중...",
                            currentStep = pipeline.currentStep ?: "",
                            completedSteps = pipeline.stepsCompleted
                        )
                    }
                    startPolling(savedId)
                } else {
                    pipelineRepository.clearSavedPipelineId()
                }
            }.onFailure {
                pipelineRepository.clearSavedPipelineId()
            }
        }
    }

    // Config setters
    fun setTopic(value: String) = _config.update { it.copy(topic = value) }
    fun setAdditionalInstructions(value: String) = _config.update { it.copy(additionalInstructions = value) }
    fun setCategory(value: String) = _config.update { it.copy(category = value) }
    fun setSlideCount(value: Int) = _config.update { it.copy(slideCount = value) }
    fun setLanguage(value: String) = _config.update { it.copy(language = value) }
    fun setVoice(value: String) = _config.update { it.copy(voice = value) }
    fun setYoutubePrivacy(value: String) = _config.update { it.copy(youtubePrivacy = value) }

    fun startPipeline() {
        val cfg = _config.value
        if (cfg.topic.isBlank() || _pipelineState.value.isRunning) return

        viewModelScope.launch {
            _pipelineState.update {
                PipelineUiState(
                    isRunning = true,
                    status = "running",
                    progress = 0,
                    message = "파이프라인 시작 중..."
                )
            }

            val pipelineConfig = PipelineConfig(
                topic = cfg.topic,
                category = cfg.category,
                targetSlides = cfg.slideCount,
                language = cfg.language,
                additionalInstructions = cfg.additionalInstructions,
                voice = cfg.voice,
                youtubePrivacy = cfg.youtubePrivacy
            )

            pipelineRepository.startPipeline(pipelineConfig)
                .onSuccess { pipelineId ->
                    _pipelineState.update { it.copy(pipelineId = pipelineId) }
                    startPolling(pipelineId)
                }
                .onFailure { error ->
                    _pipelineState.update {
                        it.copy(
                            isRunning = false,
                            status = "failed",
                            error = error.message
                        )
                    }
                }
        }
    }

    private fun startPolling(pipelineId: String) {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
            while (isActive) {
                delay(2000)
                pipelineRepository.getPipelineStatus(pipelineId)
                    .onSuccess { pipeline ->
                        _pipelineState.update { state ->
                            state.copy(
                                progress = pipeline.progress,
                                message = pipeline.message ?: "",
                                currentStep = pipeline.currentStep ?: "",
                                completedSteps = pipeline.stepsCompleted
                            )
                        }

                        when (pipeline.status) {
                            "completed" -> {
                                _pipelineState.update {
                                    it.copy(
                                        isRunning = false,
                                        status = "completed",
                                        result = PipelineResultUi(
                                            title = pipeline.result?.title,
                                            youtubeUrl = pipeline.result?.youtube?.url,
                                            duration = pipeline.duration
                                        )
                                    )
                                }
                                pipelineRepository.clearSavedPipelineId()
                                loadHistory()
                                pollingJob?.cancel()
                            }
                            "failed", "cancelled" -> {
                                _pipelineState.update {
                                    it.copy(
                                        isRunning = false,
                                        status = "failed",
                                        error = pipeline.error ?: "알 수 없는 오류가 발생했습니다."
                                    )
                                }
                                pipelineRepository.clearSavedPipelineId()
                                loadHistory()
                                pollingJob?.cancel()
                            }
                        }
                    }
            }
        }
    }

    fun cancelPipeline() {
        val pipelineId = _pipelineState.value.pipelineId ?: return
        viewModelScope.launch {
            pipelineRepository.cancelPipeline(pipelineId).onSuccess {
                _pipelineState.update {
                    it.copy(
                        isRunning = false,
                        status = "failed",
                        error = "사용자에 의해 취소됨"
                    )
                }
                pollingJob?.cancel()
                pipelineRepository.clearSavedPipelineId()
            }
        }
    }

    fun resetPipeline() {
        pollingJob?.cancel()
        _pipelineState.value = PipelineUiState()
    }

    fun logout() {
        viewModelScope.launch {
            pollingJob?.cancel()
            tokenManager.clearToken()
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollingJob?.cancel()
    }
}

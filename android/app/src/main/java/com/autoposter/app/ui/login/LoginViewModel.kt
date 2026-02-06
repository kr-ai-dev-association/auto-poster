package com.autoposter.app.ui.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.autoposter.app.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LoginUiState(
    val email: String = "",
    val password: String = "",
    val saveEmail: Boolean = false,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val isLoggedIn: Boolean = false,
    val isCheckingSession: Boolean = true
)

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val authRepository: AuthRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(LoginUiState())
    val uiState: StateFlow<LoginUiState> = _uiState.asStateFlow()

    init {
        checkExistingSession()
    }

    private fun checkExistingSession() {
        viewModelScope.launch {
            val savedEmail = authRepository.getSavedEmail()
            if (savedEmail != null) {
                _uiState.update { it.copy(email = savedEmail, saveEmail = true) }
            }

            authRepository.validateSession()
                .onSuccess {
                    _uiState.update { it.copy(isLoggedIn = true, isCheckingSession = false) }
                }
                .onFailure {
                    _uiState.update { it.copy(isCheckingSession = false) }
                }
        }
    }

    fun onEmailChange(email: String) {
        _uiState.update { it.copy(email = email, errorMessage = null) }
    }

    fun onPasswordChange(password: String) {
        _uiState.update { it.copy(password = password, errorMessage = null) }
    }

    fun onSaveEmailToggle(checked: Boolean) {
        _uiState.update { it.copy(saveEmail = checked) }
    }

    fun login() {
        val state = _uiState.value
        if (state.email.isBlank() || state.password.isBlank()) {
            _uiState.update { it.copy(errorMessage = "이메일과 비밀번호를 입력해주세요.") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null) }

            authRepository.login(state.email, state.password)
                .onSuccess {
                    if (state.saveEmail) {
                        authRepository.saveEmail(state.email)
                    } else {
                        authRepository.clearSavedEmail()
                    }
                    _uiState.update { it.copy(isLoading = false, isLoggedIn = true) }
                }
                .onFailure { error ->
                    _uiState.update {
                        it.copy(isLoading = false, errorMessage = error.message)
                    }
                }
        }
    }
}

package com.autoposter.app.data.repository

import com.autoposter.app.data.local.TokenManager
import com.autoposter.app.data.remote.api.AuthApi
import com.autoposter.app.data.remote.dto.UserResponse
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import retrofit2.HttpException
import javax.inject.Inject

class AuthRepository @Inject constructor(
    private val authApi: AuthApi,
    private val tokenManager: TokenManager
) {
    val isLoggedIn: Flow<Boolean> = tokenManager.tokenFlow.map { it != null }

    suspend fun login(email: String, password: String): Result<UserResponse> {
        return try {
            val response = authApi.login(username = email, password = password)
            tokenManager.saveToken(response.accessToken)
            val user = authApi.getMe()
            Result.success(user)
        } catch (e: HttpException) {
            val detail = when (e.code()) {
                401 -> "이메일 또는 비밀번호가 올바르지 않습니다."
                403 -> "승인 대기 중인 계정입니다."
                else -> "로그인에 실패했습니다. (${e.code()})"
            }
            Result.failure(Exception(detail))
        } catch (e: Exception) {
            Result.failure(Exception("서버에 연결할 수 없습니다."))
        }
    }

    suspend fun validateSession(): Result<UserResponse> {
        val token = tokenManager.getToken()
            ?: return Result.failure(Exception("No token"))
        return try {
            val user = authApi.getMe()
            Result.success(user)
        } catch (e: Exception) {
            tokenManager.clearToken()
            Result.failure(e)
        }
    }

    suspend fun logout() {
        tokenManager.clearToken()
    }

    suspend fun getSavedEmail(): String? = tokenManager.getSavedEmail()

    suspend fun saveEmail(email: String) = tokenManager.saveEmail(email)

    suspend fun clearSavedEmail() = tokenManager.clearSavedEmail()

    suspend fun saveCredentials(email: String, password: String) {
        tokenManager.saveEmail(email)
        tokenManager.savePassword(password)
        tokenManager.setAutoLogin(true)
    }

    suspend fun clearCredentials() = tokenManager.clearCredentials()

    suspend fun isAutoLoginEnabled(): Boolean = tokenManager.isAutoLoginEnabled()

    suspend fun tryAutoLogin(): Result<UserResponse> {
        val email = tokenManager.getSavedEmail() ?: return Result.failure(Exception("No saved email"))
        val password = tokenManager.getSavedPassword() ?: return Result.failure(Exception("No saved password"))
        return login(email, password)
    }
}

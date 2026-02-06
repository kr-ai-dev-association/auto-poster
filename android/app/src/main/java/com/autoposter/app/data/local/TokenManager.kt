package com.autoposter.app.data.local

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "auth_prefs")

@Singleton
class TokenManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private val TOKEN_KEY = stringPreferencesKey("access_token")
        private val PIPELINE_ID_KEY = stringPreferencesKey("running_pipeline_id")
        private val SAVED_EMAIL_KEY = stringPreferencesKey("saved_email")
    }

    val tokenFlow: Flow<String?> = context.dataStore.data.map { it[TOKEN_KEY] }

    suspend fun getToken(): String? = context.dataStore.data.first()[TOKEN_KEY]

    suspend fun saveToken(token: String) {
        context.dataStore.edit { it[TOKEN_KEY] = token }
    }

    suspend fun clearToken() {
        context.dataStore.edit { it.remove(TOKEN_KEY) }
    }

    suspend fun getPipelineId(): String? = context.dataStore.data.first()[PIPELINE_ID_KEY]

    suspend fun savePipelineId(id: String) {
        context.dataStore.edit { it[PIPELINE_ID_KEY] = id }
    }

    suspend fun clearPipelineId() {
        context.dataStore.edit { it.remove(PIPELINE_ID_KEY) }
    }

    suspend fun getSavedEmail(): String? = context.dataStore.data.first()[SAVED_EMAIL_KEY]

    suspend fun saveEmail(email: String) {
        context.dataStore.edit { it[SAVED_EMAIL_KEY] = email }
    }

    suspend fun clearSavedEmail() {
        context.dataStore.edit { it.remove(SAVED_EMAIL_KEY) }
    }
}

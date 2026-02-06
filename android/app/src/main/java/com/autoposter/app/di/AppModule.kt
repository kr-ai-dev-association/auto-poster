package com.autoposter.app.di

import android.content.Context
import com.autoposter.app.BuildConfig
import com.autoposter.app.data.local.TokenManager
import com.autoposter.app.data.remote.AuthInterceptor
import com.autoposter.app.data.remote.api.AuthApi
import com.autoposter.app.data.remote.api.ConfigApi
import com.autoposter.app.data.remote.api.PipelineApi
import com.autoposter.app.data.repository.AuthRepository
import com.autoposter.app.data.repository.PipelineRepository
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideTokenManager(@ApplicationContext context: Context): TokenManager =
        TokenManager(context)

    @Provides
    @Singleton
    fun provideAuthInterceptor(tokenManager: TokenManager): AuthInterceptor =
        AuthInterceptor(tokenManager)

    @Provides
    @Singleton
    fun provideOkHttpClient(authInterceptor: AuthInterceptor): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            .addInterceptor(HttpLoggingInterceptor().apply {
                level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
                else HttpLoggingInterceptor.Level.NONE
            })
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()

    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient): Retrofit =
        Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

    @Provides
    @Singleton
    fun provideAuthApi(retrofit: Retrofit): AuthApi =
        retrofit.create(AuthApi::class.java)

    @Provides
    @Singleton
    fun providePipelineApi(retrofit: Retrofit): PipelineApi =
        retrofit.create(PipelineApi::class.java)

    @Provides
    @Singleton
    fun provideConfigApi(retrofit: Retrofit): ConfigApi =
        retrofit.create(ConfigApi::class.java)

    @Provides
    @Singleton
    fun provideAuthRepository(authApi: AuthApi, tokenManager: TokenManager): AuthRepository =
        AuthRepository(authApi, tokenManager)

    @Provides
    @Singleton
    fun providePipelineRepository(pipelineApi: PipelineApi, tokenManager: TokenManager): PipelineRepository =
        PipelineRepository(pipelineApi, tokenManager)
}

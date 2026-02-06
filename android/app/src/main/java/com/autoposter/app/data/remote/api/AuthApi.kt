package com.autoposter.app.data.remote.api

import com.autoposter.app.data.remote.dto.LoginResponse
import com.autoposter.app.data.remote.dto.UserResponse
import retrofit2.http.Field
import retrofit2.http.FormUrlEncoded
import retrofit2.http.GET
import retrofit2.http.POST

interface AuthApi {

    @FormUrlEncoded
    @POST("/api/auth/login")
    suspend fun login(
        @Field("username") username: String,
        @Field("password") password: String
    ): LoginResponse

    @GET("/api/auth/me")
    suspend fun getMe(): UserResponse
}

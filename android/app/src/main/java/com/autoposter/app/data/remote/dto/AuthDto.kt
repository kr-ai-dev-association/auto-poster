package com.autoposter.app.data.remote.dto

import com.google.gson.annotations.SerializedName

data class LoginResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String
)

data class UserResponse(
    val id: Int,
    val name: String,
    val email: String,
    @SerializedName("is_super_admin") val isSuperAdmin: Boolean
)

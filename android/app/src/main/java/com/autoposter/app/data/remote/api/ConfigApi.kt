package com.autoposter.app.data.remote.api

import com.autoposter.app.data.remote.dto.CategoriesResponse
import retrofit2.http.GET

interface ConfigApi {

    @GET("/api/common/categories")
    suspend fun getCategories(): CategoriesResponse
}

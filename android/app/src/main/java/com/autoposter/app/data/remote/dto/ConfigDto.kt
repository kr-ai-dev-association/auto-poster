package com.autoposter.app.data.remote.dto

import com.google.gson.annotations.SerializedName

data class CategoriesResponse(
    val status: String,
    val categories: List<CategoryDto>
)

data class CategoryDto(
    val id: String,
    @SerializedName("name_ko") val nameKo: String,
    @SerializedName("name_en") val nameEn: String?,
    @SerializedName("description_ko") val descriptionKo: String?,
    @SerializedName("description_en") val descriptionEn: String?
)

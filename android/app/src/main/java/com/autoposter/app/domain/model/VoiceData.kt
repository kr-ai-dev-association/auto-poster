package com.autoposter.app.domain.model

data class Voice(
    val name: String,
    val gender: String,
    val description: String
)

object VoiceData {
    val voices = listOf(
        Voice("Leda", "female", "따뜻하고 친근한 여성 음성"),
        Voice("Zephyr", "male", "차분하고 신뢰감 있는 남성 음성"),
        Voice("Aoede", "female", "밝고 활기찬 여성 음성"),
        Voice("Charon", "male", "깊고 무게감 있는 남성 음성"),
        Voice("Fenrir", "male", "젊고 역동적인 남성 음성"),
        Voice("Kore", "female", "부드럽고 세련된 여성 음성"),
        Voice("Puck", "male", "캐주얼하고 친근한 남성 음성"),
        Voice("Schedar", "female", "전문적이고 명확한 여성 음성"),
    )
}

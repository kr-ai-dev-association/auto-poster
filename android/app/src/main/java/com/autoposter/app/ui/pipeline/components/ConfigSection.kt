package com.autoposter.app.ui.pipeline.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.autoposter.app.domain.model.Category
import com.autoposter.app.domain.model.Language
import com.autoposter.app.domain.model.Voice
import com.autoposter.app.ui.pipeline.ConfigState
import com.autoposter.app.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfigSection(
    config: ConfigState,
    categories: List<Category>,
    languages: List<Language>,
    voices: List<Voice>,
    slideCountOptions: List<Int>,
    isRunning: Boolean,
    onTopicChange: (String) -> Unit,
    onInstructionsChange: (String) -> Unit,
    onCategoryChange: (String) -> Unit,
    onSlideCountChange: (Int) -> Unit,
    onLanguageChange: (String) -> Unit,
    onVoiceChange: (String) -> Unit,
    onPrivacyChange: (String) -> Unit,
    onStartPipeline: () -> Unit
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = DarkSurface,
        tonalElevation = 2.dp
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Header
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = GreenAccent.copy(alpha = 0.15f),
                    modifier = Modifier.size(40.dp)
                ) {
                    Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                        Icon(
                            Icons.Default.FlashOn,
                            contentDescription = null,
                            tint = GreenAccent,
                            modifier = Modifier.size(22.dp)
                        )
                    }
                }
                Column {
                    Text(
                        "전체 자동화 파이프라인",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        color = TextPrimary
                    )
                    Text(
                        "기획 → 이미지 → PDF → 대본 → 오디오 → 비디오 → YouTube",
                        fontSize = 11.sp,
                        color = TextTertiary
                    )
                }
            }

            Divider(color = GlassBorder)

            // Topic
            Text("콘텐츠 주제/아이디어 *", style = MaterialTheme.typography.labelLarge, color = TextSecondary)
            OutlinedTextField(
                value = config.topic,
                onValueChange = onTopicChange,
                placeholder = {
                    Text(
                        "예: 2026년 최신 AI 코딩 도구 비교 분석\n\n최신 트렌드, 주요 기능, 장단점 비교 등을 포함해주세요",
                        color = TextTertiary,
                        fontSize = 13.sp
                    )
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 140.dp),
                maxLines = 10,
                colors = textFieldColors(),
                shape = RoundedCornerShape(12.dp)
            )

            // Additional instructions
            Text("추가 지시사항 (선택)", style = MaterialTheme.typography.labelLarge, color = TextSecondary)
            OutlinedTextField(
                value = config.additionalInstructions,
                onValueChange = onInstructionsChange,
                placeholder = {
                    Text("예: 초보자 대상으로 설명해주세요, 실무 예제 포함", color = TextTertiary, fontSize = 13.sp)
                },
                modifier = Modifier.fillMaxWidth(),
                maxLines = 3,
                colors = textFieldColors(),
                shape = RoundedCornerShape(12.dp)
            )

            // Category & Slide Count row
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DropdownSelector(
                    label = "카테고리",
                    selectedValue = config.category,
                    options = categories.map { it.id to it.nameKo },
                    onSelect = onCategoryChange,
                    modifier = Modifier.weight(1f)
                )
                DropdownSelector(
                    label = "슬라이드 수",
                    selectedValue = config.slideCount.toString(),
                    options = slideCountOptions.map { it.toString() to "${it}장" },
                    onSelect = { onSlideCountChange(it.toInt()) },
                    modifier = Modifier.weight(1f)
                )
            }

            // Language & Voice row
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DropdownSelector(
                    label = "언어",
                    selectedValue = config.language,
                    options = languages.map { it.id to it.nameKo },
                    onSelect = onLanguageChange,
                    modifier = Modifier.weight(1f)
                )
                DropdownSelector(
                    label = "TTS 음성",
                    selectedValue = config.voice,
                    options = voices.map { it.name to "${it.name} (${it.gender})" },
                    onSelect = onVoiceChange,
                    modifier = Modifier.weight(1f)
                )
            }

            // YouTube privacy
            YouTubePrivacySelector(
                selected = config.youtubePrivacy,
                onSelect = onPrivacyChange
            )

            // Start button
            Button(
                onClick = onStartPipeline,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                enabled = config.topic.isNotBlank() && !isRunning,
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = GreenAccent,
                    disabledContainerColor = DarkSurfaceVariant
                )
            ) {
                if (isRunning) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(22.dp),
                        color = TextPrimary,
                        strokeWidth = 2.dp
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("파이프라인 실행 중...", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                } else {
                    Icon(Icons.Default.FlashOn, contentDescription = null, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("전체 자동화 시작", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DropdownSelector(
    label: String,
    selectedValue: String,
    options: List<Pair<String, String>>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedLabel = options.find { it.first == selectedValue }?.second ?: selectedValue

    Column(modifier = modifier) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = TextSecondary)
        Spacer(Modifier.height(4.dp))
        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = !expanded }
        ) {
            OutlinedTextField(
                value = selectedLabel,
                onValueChange = {},
                readOnly = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                modifier = Modifier
                    .menuAnchor()
                    .fillMaxWidth(),
                colors = textFieldColors(),
                shape = RoundedCornerShape(12.dp),
                textStyle = MaterialTheme.typography.bodyMedium
            )
            ExposedDropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
                modifier = Modifier.exposedDropdownSize()
            ) {
                options.forEach { (value, display) ->
                    DropdownMenuItem(
                        text = { Text(display, color = TextPrimary) },
                        onClick = {
                            onSelect(value)
                            expanded = false
                        },
                        contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding
                    )
                }
            }
        }
    }
}

@Composable
private fun textFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = GreenAccent,
    unfocusedBorderColor = DarkBorder,
    focusedLabelColor = GreenAccent,
    unfocusedLabelColor = TextTertiary,
    cursorColor = GreenAccent,
    focusedTextColor = TextPrimary,
    unfocusedTextColor = TextPrimary
)

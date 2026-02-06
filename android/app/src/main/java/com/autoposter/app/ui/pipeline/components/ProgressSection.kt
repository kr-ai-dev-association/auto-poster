package com.autoposter.app.ui.pipeline.components

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Pending
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.autoposter.app.domain.model.PipelineStepId
import com.autoposter.app.domain.model.PipelineUiState
import com.autoposter.app.ui.theme.*

@Composable
fun ProgressSection(
    state: PipelineUiState,
    steps: List<PipelineStepId>,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = DarkSurface,
        tonalElevation = 2.dp
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(
                "파이프라인 진행 상황",
                fontWeight = FontWeight.SemiBold,
                fontSize = 16.sp,
                color = TextPrimary
            )

            if (state.pipelineId != null) {
                // Stepper
                StepperIndicator(
                    steps = steps,
                    currentStep = state.currentStep,
                    completedSteps = state.completedSteps
                )

                Spacer(Modifier.height(4.dp))

                // Progress info
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = state.message.ifBlank { "대기 중..." },
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        text = "${state.progress}%",
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.Bold
                        ),
                        color = TextPrimary
                    )
                }

                // Progress bar
                val animatedProgress by animateFloatAsState(
                    targetValue = state.progress / 100f,
                    animationSpec = tween(500),
                    label = "progress"
                )

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(16.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(DarkSurfaceVariant)
                ) {
                    val barBrush = when (state.status) {
                        "completed" -> Brush.horizontalGradient(listOf(GreenAccent, GreenAccent))
                        "failed" -> Brush.horizontalGradient(listOf(RedError, RedError))
                        else -> Brush.horizontalGradient(listOf(BluePrimary, IndigoPrimary))
                    }
                    Box(
                        modifier = Modifier
                            .fillMaxHeight()
                            .fillMaxWidth(animatedProgress)
                            .clip(RoundedCornerShape(8.dp))
                            .background(barBrush)
                            .animateContentSize()
                    )
                }

                // Cancel button
                if (state.isRunning) {
                    OutlinedButton(
                        onClick = onCancel,
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = RedLight
                        ),
                        border = ButtonDefaults.outlinedButtonBorder.copy(
                            brush = Brush.linearGradient(listOf(RedError.copy(alpha = 0.5f), RedError.copy(alpha = 0.5f)))
                        )
                    ) {
                        Icon(Icons.Default.Close, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("파이프라인 취소")
                    }
                }
            } else {
                // Waiting state
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(
                        Icons.Default.Pending,
                        contentDescription = null,
                        tint = TextTertiary,
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "주제를 입력하고 자동화를 시작하세요",
                        color = TextTertiary,
                        fontSize = 14.sp
                    )
                    Text(
                        "전체 과정이 자동으로 진행됩니다",
                        color = TextTertiary.copy(alpha = 0.7f),
                        fontSize = 12.sp
                    )
                }
            }
        }
    }
}

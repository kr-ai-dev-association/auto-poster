package com.autoposter.app.ui.pipeline.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.autoposter.app.domain.model.PipelineStepId
import com.autoposter.app.ui.theme.*

@Composable
fun StepperIndicator(
    steps: List<PipelineStepId>,
    currentStep: String,
    completedSteps: List<String>,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top
    ) {
        steps.forEachIndexed { index, step ->
            val isCompleted = step.id in completedSteps
            val isCurrent = step.id == currentStep

            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.weight(1f)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // Connector line (left)
                    if (index > 0) {
                        val prevCompleted = steps[index - 1].id in completedSteps
                        val lineColor by animateColorAsState(
                            targetValue = if (prevCompleted) GreenAccent else DarkSurfaceVariant,
                            label = "lineColor"
                        )
                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .height(2.dp)
                                .background(lineColor)
                        )
                    }

                    // Step circle
                    StepCircle(
                        isCompleted = isCompleted,
                        isCurrent = isCurrent
                    )

                    // Connector line (right)
                    if (index < steps.lastIndex) {
                        val lineColor by animateColorAsState(
                            targetValue = if (isCompleted) GreenAccent else DarkSurfaceVariant,
                            label = "lineColor"
                        )
                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .height(2.dp)
                                .background(lineColor)
                        )
                    }
                }

                Spacer(Modifier.height(4.dp))

                // Label
                val labelColor by animateColorAsState(
                    targetValue = when {
                        isCompleted -> GreenLight
                        isCurrent -> BlueLight
                        else -> TextTertiary
                    },
                    label = "labelColor"
                )
                Text(
                    text = step.label,
                    fontSize = 9.sp,
                    color = labelColor,
                    textAlign = TextAlign.Center,
                    fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal,
                    maxLines = 1
                )
            }
        }
    }
}

@Composable
private fun StepCircle(isCompleted: Boolean, isCurrent: Boolean) {
    val bgColor by animateColorAsState(
        targetValue = when {
            isCompleted -> GreenAccent
            isCurrent -> BluePrimary
            else -> DarkSurfaceVariant
        },
        label = "bgColor"
    )

    // Pulse animation for current step
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = EaseInOut),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulseAlpha"
    )

    val size = 28.dp
    val shadowModifier = if (isCurrent) {
        Modifier.shadow(8.dp, CircleShape, ambientColor = BluePrimary.copy(alpha = 0.5f))
    } else Modifier

    Box(
        modifier = shadowModifier
            .size(size)
            .clip(CircleShape)
            .background(
                if (isCurrent) bgColor.copy(alpha = pulseAlpha)
                else bgColor
            ),
        contentAlignment = Alignment.Center
    ) {
        if (isCompleted) {
            Icon(
                Icons.Default.Check,
                contentDescription = null,
                tint = TextPrimary,
                modifier = Modifier.size(16.dp)
            )
        } else if (isCurrent) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(TextPrimary)
            )
        }
    }
}

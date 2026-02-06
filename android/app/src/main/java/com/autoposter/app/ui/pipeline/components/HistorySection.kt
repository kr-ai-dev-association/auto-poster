package com.autoposter.app.ui.pipeline.components

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.History
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.autoposter.app.domain.model.PipelineHistoryItem
import com.autoposter.app.ui.theme.*

@Composable
fun HistorySection(
    history: List<PipelineHistoryItem>,
    modifier: Modifier = Modifier
) {
    if (history.isEmpty()) return

    val context = LocalContext.current

    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = DarkSurface,
        tonalElevation = 2.dp
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    Icons.Default.History,
                    contentDescription = null,
                    tint = TextTertiary,
                    modifier = Modifier.size(18.dp)
                )
                Text(
                    "최근 파이프라인",
                    style = MaterialTheme.typography.labelLarge,
                    color = TextSecondary
                )
            }

            Spacer(Modifier.height(12.dp))

            history.forEach { item ->
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 3.dp),
                    shape = RoundedCornerShape(10.dp),
                    color = DarkSurfaceVariant.copy(alpha = 0.5f)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Status dot
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(
                                    if (item.status == "completed") GreenAccent else RedError
                                )
                        )

                        Spacer(Modifier.width(10.dp))

                        // Title/topic
                        Text(
                            text = item.title ?: item.topic ?: "제목 없음",
                            color = TextSecondary,
                            fontSize = 13.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f)
                        )

                        // YouTube link
                        if (!item.youtubeUrl.isNullOrBlank()) {
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = "YouTube",
                                color = BlueLight,
                                fontSize = 12.sp,
                                modifier = Modifier.clickable {
                                    context.startActivity(
                                        Intent(Intent.ACTION_VIEW, Uri.parse(item.youtubeUrl))
                                    )
                                }
                            )
                        }
                    }
                }
            }
        }
    }
}

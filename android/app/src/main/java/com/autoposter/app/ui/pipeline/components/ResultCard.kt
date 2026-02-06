package com.autoposter.app.ui.pipeline.components

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.autoposter.app.domain.model.PipelineResultUi
import com.autoposter.app.ui.theme.*

@Composable
fun CompletionCard(
    result: PipelineResultUi,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current

    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = GreenBg,
        border = BorderStroke(1.dp, GreenDark.copy(alpha = 0.5f))
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    Icons.Default.CheckCircle,
                    contentDescription = null,
                    tint = GreenLight,
                    modifier = Modifier.size(24.dp)
                )
                Text(
                    "파이프라인 완료!",
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 18.sp,
                    color = GreenLight
                )
            }

            // Title
            if (!result.title.isNullOrBlank()) {
                Column {
                    Text("제목", fontSize = 11.sp, color = TextTertiary)
                    Text(result.title, color = TextPrimary, fontWeight = FontWeight.Medium)
                }
            }

            // YouTube URL
            if (!result.youtubeUrl.isNullOrBlank()) {
                Column {
                    Text("YouTube 링크", fontSize = 11.sp, color = TextTertiary)
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.clickable {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(result.youtubeUrl)))
                        }
                    ) {
                        Text(
                            text = result.youtubeUrl,
                            color = BlueLight,
                            textDecoration = TextDecoration.Underline,
                            fontSize = 14.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f)
                        )
                        Spacer(Modifier.width(4.dp))
                        Icon(
                            Icons.Default.OpenInNew,
                            contentDescription = null,
                            tint = BlueLight,
                            modifier = Modifier.size(16.dp)
                        )
                    }
                }
            }

            // Duration
            if (!result.duration.isNullOrBlank()) {
                Column {
                    Text("소요 시간", fontSize = 11.sp, color = TextTertiary)
                    Text(result.duration, color = TextPrimary, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

@Composable
fun ErrorCard(
    error: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = RedBg,
        border = BorderStroke(1.dp, RedError.copy(alpha = 0.5f))
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    Icons.Default.Error,
                    contentDescription = null,
                    tint = RedLight,
                    modifier = Modifier.size(24.dp)
                )
                Text(
                    "파이프라인 실패",
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 18.sp,
                    color = RedLight
                )
            }

            Surface(
                shape = RoundedCornerShape(8.dp),
                color = RedError.copy(alpha = 0.15f)
            ) {
                Text(
                    text = error,
                    color = RedLight,
                    fontSize = 13.sp,
                    modifier = Modifier.padding(12.dp)
                )
            }

            Button(
                onClick = onRetry,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = DarkSurfaceVariant)
            ) {
                Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("다시 시도")
            }
        }
    }
}

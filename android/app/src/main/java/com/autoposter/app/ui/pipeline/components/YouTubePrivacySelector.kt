package com.autoposter.app.ui.pipeline.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.YouTube
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.autoposter.app.ui.theme.*

private data class PrivacyOption(
    val value: String,
    val label: String
)

private val privacyOptions = listOf(
    PrivacyOption("private", "비공개"),
    PrivacyOption("unlisted", "일부 공개"),
    PrivacyOption("public", "공개"),
)

@Composable
fun YouTubePrivacySelector(
    selected: String,
    onSelect: (String) -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Icon(
                Icons.Default.YouTube,
                contentDescription = null,
                tint = RedError,
                modifier = Modifier.size(18.dp)
            )
            Text(
                "YouTube 업로드 설정",
                style = MaterialTheme.typography.labelLarge,
                color = TextSecondary
            )
        }

        SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
            privacyOptions.forEachIndexed { index, option ->
                SegmentedButton(
                    selected = selected == option.value,
                    onClick = { onSelect(option.value) },
                    shape = SegmentedButtonDefaults.itemShape(
                        index = index,
                        count = privacyOptions.size,
                        baseShape = RoundedCornerShape(12.dp)
                    ),
                    colors = SegmentedButtonDefaults.colors(
                        activeContainerColor = IndigoPrimary.copy(alpha = 0.3f),
                        activeContentColor = IndigoLight,
                        inactiveContainerColor = DarkSurfaceVariant.copy(alpha = 0.5f),
                        inactiveContentColor = TextSecondary,
                        activeBorderColor = IndigoPrimary,
                        inactiveBorderColor = DarkBorder
                    )
                ) {
                    Text(
                        option.label,
                        fontSize = 13.sp,
                        fontWeight = if (selected == option.value) FontWeight.SemiBold else FontWeight.Normal
                    )
                }
            }
        }
    }
}

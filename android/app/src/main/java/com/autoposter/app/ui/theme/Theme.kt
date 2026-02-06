package com.autoposter.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val DarkColorScheme = darkColorScheme(
    primary = IndigoPrimary,
    onPrimary = TextPrimary,
    secondary = GreenAccent,
    onSecondary = TextPrimary,
    tertiary = BluePrimary,
    background = DarkBackground,
    onBackground = TextPrimary,
    surface = DarkSurface,
    onSurface = TextPrimary,
    surfaceVariant = DarkSurfaceVariant,
    onSurfaceVariant = TextSecondary,
    error = RedError,
    onError = TextPrimary,
    outline = DarkBorder,
    outlineVariant = GlassBorder
)

@Composable
fun AutoPosterTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = Typography,
        content = content
    )
}

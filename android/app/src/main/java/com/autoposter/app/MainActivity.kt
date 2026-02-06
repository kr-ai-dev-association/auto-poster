package com.autoposter.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.navigation.compose.rememberNavController
import com.autoposter.app.ui.navigation.NavGraph
import com.autoposter.app.ui.theme.AutoPosterTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AutoPosterTheme {
                val navController = rememberNavController()
                NavGraph(navController = navController)
            }
        }
    }
}

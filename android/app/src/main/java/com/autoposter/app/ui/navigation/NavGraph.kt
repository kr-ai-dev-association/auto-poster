package com.autoposter.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.autoposter.app.ui.login.LoginScreen
import com.autoposter.app.ui.login.LoginViewModel
import com.autoposter.app.ui.pipeline.PipelineScreen
import com.autoposter.app.ui.pipeline.PipelineViewModel

sealed class Screen(val route: String) {
    data object Login : Screen("login")
    data object Pipeline : Screen("pipeline")
}

@Composable
fun NavGraph(navController: NavHostController) {
    NavHost(
        navController = navController,
        startDestination = Screen.Login.route
    ) {
        composable(Screen.Login.route) {
            val viewModel: LoginViewModel = hiltViewModel()
            val uiState by viewModel.uiState.collectAsStateWithLifecycle()

            LaunchedEffect(uiState.isLoggedIn) {
                if (uiState.isLoggedIn) {
                    navController.navigate(Screen.Pipeline.route) {
                        popUpTo(Screen.Login.route) { inclusive = true }
                    }
                }
            }

            LoginScreen(viewModel = viewModel)
        }

        composable(Screen.Pipeline.route) {
            val viewModel: PipelineViewModel = hiltViewModel()

            PipelineScreen(
                viewModel = viewModel,
                onLogout = {
                    viewModel.logout()
                    navController.navigate(Screen.Login.route) {
                        popUpTo(Screen.Pipeline.route) { inclusive = true }
                    }
                }
            )
        }
    }
}

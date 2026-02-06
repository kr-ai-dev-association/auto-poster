# Retrofit
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.autoposter.app.data.remote.dto.** { *; }
-keepclassmembers class com.autoposter.app.data.remote.dto.** { *; }

# Gson
-keep class com.google.gson.** { *; }
-keepattributes EnclosingMethod

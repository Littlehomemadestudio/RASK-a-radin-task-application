# Keep Room generated code
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep @androidx.room.Entity class * { *; }
-keep class androidx.room.* { *; }

# Keep LiveData / ViewModel
-keep class androidx.lifecycle.** { *; }
-keep class * extends androidx.lifecycle.ViewModel { <init>(); }
-keep class * extends androidx.lifecycle.AndroidViewModel { <init>(); }

# Keep DataStore
-keep class androidx.datastore.** { *; }

# Keep MPAndroidChart
-keep class com.github.mikephil.charting.** { *; }
-dontwarn com.github.mikephil.charting.**

# Kotlin coroutines
-dontwarn kotlinx.coroutines.**
-keepclassmembernames class kotlinx.** { volatile <fields>; }

# Reflection — Kotlin metadata
-keepattributes RuntimeVisibleAnnotations,AnnotationDefault,Signature,InnerClasses,EnclosingMethod
-keep class kotlin.Metadata { *; }

# Application class
-keep class com.rask.app.RaskApplication { *; }

# Room DAO interfaces (called reflectively by generated impl)
-keep interface com.rask.app.data.db.dao.** { *; }

# Backup model classes serialized to JSON
-keep class com.rask.app.data.backup.** { *; }
-keep class com.rask.app.data.db.entity.** { *; }

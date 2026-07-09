package com.rask.app.ui.onboarding

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.rask.app.R
import com.rask.app.RaskApplication
import com.rask.app.databinding.ActivityOnboardingBinding
import com.rask.app.ui.main.MainActivity
import com.rask.app.utils.LocaleHelper
import kotlinx.coroutines.launch

/**
 * 3-screen onboarding.
 *
 * Page 0: Track time, beautifully
 * Page 1: Goals that breathe with you
 * Page 2: Insight, not noise
 *
 * Final screen swaps the CTA label to "Get started" and writes
 * onboardingCompleted = true to DataStore before launching MainActivity.
 */
class OnboardingActivity : AppCompatActivity() {

    private lateinit var binding: ActivityOnboardingBinding

    private data class Slide(
        val illustration: Int,
        val titleRes: Int,
        val bodyRes: Int
    )

    private val slides = listOf(
        Slide(R.drawable.illustration_onboarding_1, R.string.onboarding_1_title, R.string.onboarding_1_body),
        Slide(R.drawable.illustration_onboarding_2, R.string.onboarding_2_title, R.string.onboarding_2_body),
        Slide(R.drawable.illustration_onboarding_3, R.string.onboarding_3_title, R.string.onboarding_3_body)
    )

    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityOnboardingBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Initial state
        renderSlide(0)

        binding.btnContinue.setOnClickListener {
            val next = (binding.illustration.tag as? Int ?: 0) + 1
            if (next < slides.size) {
                renderSlide(next)
            } else {
                finishOnboarding()
            }
        }

        binding.btnSkip.setOnClickListener {
            finishOnboarding()
        }
    }

    private fun renderSlide(index: Int) {
        val slide = slides[index]
        binding.illustration.setImageResource(slide.illustration)
        binding.illustration.tag = index
        binding.headline.setText(slide.titleRes)
        binding.body.setText(slide.bodyRes)

        // Fade in/out
        binding.illustration.alpha = 0f
        binding.headline.alpha = 0f
        binding.body.alpha = 0f
        binding.illustration.animate().alpha(1f).setDuration(280).start()
        binding.headline.animate().alpha(1f).setDuration(280).setStartDelay(60).start()
        binding.body.animate().alpha(1f).setDuration(280).setStartDelay(120).start()

        // Pager dots
        val dots = listOf(binding.dot0, binding.dot1, binding.dot2)
        dots.forEachIndexed { i, v ->
            v.setBackgroundResource(
                if (i == index) R.drawable.onboarding_dot_active
                else R.drawable.onboarding_dot_inactive
            )
        }

        // CTA label changes on last slide
        binding.btnContinue.setText(
            if (index == slides.lastIndex) R.string.onboarding_start
            else R.string.onboarding_next
        )
    }

    private fun finishOnboarding() {
        lifecycleScope.launch {
            val app = application as RaskApplication
            app.prefs.setOnboardingCompleted(true)
            startActivity(Intent(this@OnboardingActivity, MainActivity::class.java))
            finish()
        }
    }
}

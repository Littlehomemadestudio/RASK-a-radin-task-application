package com.rask.app.ui.home

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import com.rask.app.R
import com.rask.app.databinding.FragmentHomeBinding
import com.rask.app.service.TimerService
import com.rask.app.utils.DateUtils
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Home screen — today hero card, goal rings, recent activities, and (when active)
 * the live timer panel with pause/stop controls.
 */
class HomeFragment : Fragment() {

    private var _binding: FragmentHomeBinding? = null
    private val binding get() = _binding!!

    private val vm: HomeViewModel by viewModels()
    private lateinit var recentAdapter: RecentActivitiesAdapter
    private lateinit var goalsAdapter: GoalsAdapter

    private var tickerJob: kotlinx.coroutines.Job? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentHomeBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Recent activities
        recentAdapter = RecentActivitiesAdapter()
        binding.recentList.layoutManager = LinearLayoutManager(requireContext())
        binding.recentList.adapter = recentAdapter

        // Goals
        goalsAdapter = GoalsAdapter()
        binding.goalsList.layoutManager = LinearLayoutManager(requireContext())
        binding.goalsList.adapter = goalsAdapter

        // Observe VM
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { vm.todayTotal.observe { total ->
                    binding.todayTotal.text = DateUtils.durationLabel(total)
                    val target = vm.todayTarget.value ?: 0L
                    if (target > 0L) {
                        val ratio = (total.toFloat() / target.toFloat()).coerceIn(0f, 1f)
                        binding.todayRing.setProgress(ratio)
                        binding.todaySubtitle.text = getString(
                            R.string.goals_remaining,
                            DateUtils.durationLabel((target - total).coerceAtLeast(0))
                        )
                    } else {
                        binding.todayRing.setProgress(0f)
                        binding.todaySubtitle.text = ""
                    }
                }}
                launch { vm.todayTarget.observe { target ->
                    val total = vm.todayTotal.value ?: 0L
                    if (target > 0L) {
                        val ratio = (total.toFloat() / target.toFloat()).coerceIn(0f, 1f)
                        binding.todayRing.setProgress(ratio)
                        binding.todaySubtitle.text = getString(
                            R.string.goals_remaining,
                            DateUtils.durationLabel((target - total).coerceAtLeast(0))
                        )
                    } else {
                        binding.todayRing.setProgress(0f)
                        binding.todaySubtitle.text = ""
                    }
                }}
                launch { vm.recent.observe { acts ->
                    recentAdapter.submit(acts)
                    binding.emptyState.visibility =
                        if (acts.isEmpty()) View.VISIBLE else View.GONE
                }}
                launch { vm.goalProgress.observe { goalsAdapter.submit(it) } }

                // Timer
                launch { vm.timerRunning.observe { running ->
                    binding.timerPanel.visibility = if (running) View.VISIBLE else View.GONE
                    if (running) startTicker() else stopTicker()
                }}
                launch { vm.timerPaused.observe { paused ->
                    binding.btnTimerPause.text = getString(
                        if (paused) R.string.timer_resume else R.string.timer_pause
                    )
                    binding.btnTimerPause.setIconResource(
                        if (paused) R.drawable.ic_play else R.drawable.ic_pause
                    )
                }}
                launch { vm.timerElapsed.observe { elapsed ->
                    binding.timerDisplay.text = DateUtils.millisToHhMmSs(elapsed)
                }}
            }
        }

        // Buttons
        binding.btnTimerPause.setOnClickListener {
            val paused = vm.timerPaused.value == true
            if (paused) TimerService.resume(requireContext())
            else TimerService.pause(requireContext())
        }
        binding.btnTimerStop.setOnClickListener {
            TimerService.stop(requireContext())
        }
    }

    /**
     * Run a 1Hz ticker so the on-screen timer display updates smoothly while
     * the user is on the Home tab.
     */
    private fun startTicker() {
        if (tickerJob?.isActive == true) return
        tickerJob = viewLifecycleOwner.lifecycleScope.launch {
            val app = (requireActivity().application as com.rask.app.RaskApplication)
            while (true) {
                val startedIso = app.prefs.timerStartedAt.first()
                val pausedIso = app.prefs.timerPausedAt.first()
                val accumulated = app.prefs.timerAccumulatedMs.first()
                if (startedIso.isBlank()) break
                val delta = if (pausedIso.isNotBlank()) {
                    DateUtils.between(startedIso, pausedIso)
                } else {
                    DateUtils.between(startedIso, DateUtils.nowUtcIso())
                }
                binding.timerDisplay.text = DateUtils.millisToHhMmSs(accumulated + delta)
                kotlinx.coroutines.delay(1000)
            }
        }
    }

    private fun stopTicker() {
        tickerJob?.cancel()
        tickerJob = null
    }

    override fun onDestroyView() {
        super.onDestroyView()
        stopTicker()
        _binding = null
    }
}

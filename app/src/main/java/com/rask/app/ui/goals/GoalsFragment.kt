package com.rask.app.ui.goals

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.rask.app.R
import com.rask.app.data.db.entity.GoalEntity
import com.rask.app.databinding.FragmentGoalsBinding
import com.rask.app.utils.DateUtils
import com.rask.app.utils.Haptics
import kotlinx.coroutines.launch

class GoalsFragment : Fragment() {

    private var _binding: FragmentGoalsBinding? = null
    private val binding get() = _binding!!
    private val vm: GoalsViewModel by viewModels()
    private lateinit var adapter: GoalsListAdapter

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentGoalsBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        adapter = GoalsListAdapter(
            onDelete = { id ->
                MaterialAlertDialogBuilder(requireContext())
                    .setTitle(R.string.delete)
                    .setMessage(R.string.goals_title)
                    .setNegativeButton(R.string.cancel, null)
                    .setPositiveButton(R.string.delete) { _, _ -> vm.deleteGoal(id) }
                    .show()
            }
        )
        binding.goalsList.layoutManager = LinearLayoutManager(requireContext())
        binding.goalsList.adapter = adapter

        binding.fabAdd.setOnClickListener { showAddDialog() }

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { vm.goals.observe { goals ->
                    adapter.submit(goals, vm.progress.value ?: emptyMap(), vm.streaks.value ?: emptyMap())
                    binding.emptyState.visibility = if (goals.isEmpty()) View.VISIBLE else View.GONE
                }}
                launch { vm.progress.observe { adapter.updateProgress(it) }}
                launch { vm.streaks.observe { adapter.updateStreaks(it) }}
            }
        }
    }

    private fun showAddDialog() {
        val view = LayoutInflater.from(requireContext())
            .inflate(R.layout.dialog_goal, null, false)

        // Scope dropdown
        val scopes = listOf(
            GoalEntity.SCOPE_DAILY to getString(R.string.goals_scope_daily),
            GoalEntity.SCOPE_WEEKLY to getString(R.string.goals_scope_weekly),
            GoalEntity.SCOPE_MONTHLY to getString(R.string.goals_scope_monthly)
        )
        val scopeLabels = scopes.map { it.second }
        val scopeAdapter = ArrayAdapter(
            requireContext(),
            android.R.layout.simple_list_item_1,
            scopeLabels
        )
        view.findViewById<android.widget.AutoCompleteTextView>(R.id.scopeInput)
            .apply {
                setAdapter(scopeAdapter)
                threshold = 1
                setText(scopeLabels[0], false)
            }

        val dialog = MaterialAlertDialogBuilder(requireContext())
            .setTitle(R.string.goals_add)
            .setView(view)
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.save, null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val scopePos = scopeLabels.indexOf(
                    view.findViewById<android.widget.AutoCompleteTextView>(R.id.scopeInput).text.toString()
                )
                val scope = scopes.getOrElse(scopePos) { scopes[0] }.first
                val hours = view.findViewById<android.widget.EditText>(R.id.hoursInput)
                    .text.toString().toLongOrNull() ?: 0L
                val minutes = view.findViewById<android.widget.EditText>(R.id.minutesInput)
                    .text.toString().toLongOrNull() ?: 0L
                val totalMs = (hours * 3_600_000L) + (minutes * 60_000L)
                if (totalMs <= 0L) return@setOnClickListener
                vm.addGoal(scope, totalMs, categoryId = null, name = null)
                Haptics.tick(requireContext())
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    override fun onResume() {
        super.onResume()
        vm.recompute()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}

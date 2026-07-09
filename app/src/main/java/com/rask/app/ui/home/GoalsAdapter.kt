package com.rask.app.ui.home

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.rask.app.databinding.ItemGoalProgressBinding
import com.rask.app.utils.DateUtils

/**
 * Per-goal horizontal ring + label list on Home.
 */
class GoalsAdapter :
    ListAdapter<HomeViewModel.GoalProgress, GoalsAdapter.VH>(DIFF) {

    fun submit(items: List<HomeViewModel.GoalProgress>) {
        submitList(items.toList())
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val b = ItemGoalProgressBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(b)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(getItem(position))
    }

    inner class VH(private val b: ItemGoalProgressBinding) :
        RecyclerView.ViewHolder(b.root) {
        fun bind(p: HomeViewModel.GoalProgress) {
            b.label.text = p.goal.name ?: b.root.context.getString(
                com.rask.app.R.string.goals_overall
            )
            b.progressLabel.text = b.root.context.getString(
                com.rask.app.R.string.time_hh_mm,
                DateUtils.millisToHhMm(p.progressMillis).first.toString(),
                DateUtils.millisToHhMm(p.progressMillis).second.toString()
            ) + " / " + DateUtils.durationLabel(p.goal.targetMillis)
            b.ring.setProgress(p.ratio)
            if (p.streak >= 3) {
                b.streakLabel.visibility = android.view.View.VISIBLE
                b.streakLabel.text = b.root.context.getString(
                    com.rask.app.R.string.home_streak, p.streak
                )
            } else {
                b.streakLabel.visibility = android.view.View.GONE
            }
        }
    }

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<HomeViewModel.GoalProgress>() {
            override fun areItemsTheSame(
                o: HomeViewModel.GoalProgress, n: HomeViewModel.GoalProgress
            ) = o.goal.id == n.goal.id
            override fun areContentsTheSame(
                o: HomeViewModel.GoalProgress, n: HomeViewModel.GoalProgress
            ) = o == n
        }
    }
}

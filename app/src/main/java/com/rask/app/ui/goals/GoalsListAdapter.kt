package com.rask.app.ui.goals

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.rask.app.data.db.entity.GoalEntity
import com.rask.app.data.db.entity.StreakEntity
import com.rask.app.databinding.ItemGoalCardBinding
import com.rask.app.utils.DateUtils

class GoalsListAdapter(
    private val onDelete: (Long) -> Unit
) : ListAdapter<GoalEntity, GoalsListAdapter.VH>(DIFF) {

    private var progressMap: Map<Long, Long> = emptyMap()
    private var streakMap: Map<Long, StreakEntity> = emptyMap()

    fun submit(
        goals: List<GoalEntity>,
        progress: Map<Long, Long>,
        streaks: Map<Long, StreakEntity>
    ) {
        progressMap = progress
        streakMap = streaks
        submitList(goals.toList())
    }

    fun updateProgress(p: Map<Long, Long>) {
        progressMap = p
        notifyDataSetChanged()
    }

    fun updateStreaks(s: Map<Long, StreakEntity>) {
        streakMap = s
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val b = ItemGoalCardBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(b)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(getItem(position))
    }

    inner class VH(private val b: ItemGoalCardBinding) :
        RecyclerView.ViewHolder(b.root) {
        init {
            b.btnDelete.setOnClickListener {
                val pos = bindingAdapterPosition
                if (pos != RecyclerView.NO_POSITION) onDelete(getItem(pos).id)
            }
        }
        fun bind(g: GoalEntity) {
            val scopeLabel = when (g.scope) {
                GoalEntity.SCOPE_DAILY -> b.root.context.getString(com.rask.app.R.string.goals_scope_daily)
                GoalEntity.SCOPE_WEEKLY -> b.root.context.getString(com.rask.app.R.string.goals_scope_weekly)
                GoalEntity.SCOPE_MONTHLY -> b.root.context.getString(com.rask.app.R.string.goals_scope_monthly)
                else -> ""
            }
            b.label.text = (g.name ?: b.root.context.getString(com.rask.app.R.string.goals_overall)) + " · " + scopeLabel
            val progress = progressMap[g.id] ?: 0L
            val ratio = if (g.targetMillis > 0)
                (progress.toFloat() / g.targetMillis.toFloat()).coerceIn(0f, 1f) else 0f
            b.ring.setProgress(ratio)
            b.progressLabel.text = b.root.context.getString(
                com.rask.app.R.string.time_hh_mm,
                DateUtils.millisToHhMm(progress).first.toString(),
                DateUtils.millisToHhMm(progress).second.toString()
            ) + " / " + DateUtils.durationLabel(g.targetMillis)
            val streak = streakMap[g.id]
            if (streak != null && streak.current > 0) {
                b.streakLabel.visibility = android.view.View.VISIBLE
                b.streakLabel.text = b.root.context.getString(
                    com.rask.app.R.string.home_streak, streak.current
                )
            } else {
                b.streakLabel.visibility = android.view.View.GONE
            }
            if (progress >= g.targetMillis && g.targetMillis > 0L) {
                b.statusLabel.visibility = android.view.View.VISIBLE
                b.statusLabel.text = b.root.context.getString(com.rask.app.R.string.goals_reached)
            } else {
                b.statusLabel.visibility = android.view.View.GONE
            }
        }
    }

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<GoalEntity>() {
            override fun areItemsTheSame(o: GoalEntity, n: GoalEntity) = o.id == n.id
            override fun areContentsTheSame(o: GoalEntity, n: GoalEntity) = o == n
        }
    }
}

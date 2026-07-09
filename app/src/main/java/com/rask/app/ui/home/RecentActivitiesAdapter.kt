package com.rask.app.ui.home

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.rask.app.data.db.entity.ActivityEntity
import com.rask.app.databinding.ItemRecentActivityBinding
import com.rask.app.utils.DateUtils

/**
 * Recent activities list shown on the Home tab.
 */
class RecentActivitiesAdapter :
    ListAdapter<ActivityEntity, RecentActivitiesAdapter.VH>(DIFF) {

    fun submit(items: List<ActivityEntity>) {
        submitList(items.toList())
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val b = ItemRecentActivityBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(b)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(getItem(position))
    }

    inner class VH(private val b: ItemRecentActivityBinding) :
        RecyclerView.ViewHolder(b.root) {
        fun bind(a: ActivityEntity) {
            b.title.text = a.title
            b.duration.text = DateUtils.durationLabel(a.durationMillis)
            val local = DateUtils.fromUtcIso(a.startedAt)
            b.timestamp.text = DateUtils.shortDate(local) + " · " + DateUtils.shortTime(local)
            b.categoryLabel.text = a.category ?: ""
            b.categoryLabel.visibility =
                if (a.category.isNullOrBlank()) android.view.View.GONE else android.view.View.VISIBLE
        }
    }

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<ActivityEntity>() {
            override fun areItemsTheSame(o: ActivityEntity, n: ActivityEntity) = o.id == n.id
            override fun areContentsTheSame(o: ActivityEntity, n: ActivityEntity) = o == n
        }
    }
}

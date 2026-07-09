package com.rask.app.ui.home

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.rask.app.data.db.entity.TemplateEntity
import com.rask.app.databinding.ItemTemplateBinding

/**
 * Horizontal chip-like list of templates in the QuickLog dialog.
 */
class TemplatesAdapter(
    private val onClick: (TemplateEntity) -> Unit
) : ListAdapter<TemplateEntity, TemplatesAdapter.VH>(DIFF) {

    fun submit(items: List<TemplateEntity>) {
        submitList(items)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val b = ItemTemplateBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(b)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(getItem(position))
    }

    inner class VH(private val b: ItemTemplateBinding) :
        RecyclerView.ViewHolder(b.root) {
        init { b.root.setOnClickListener { 
            val pos = bindingAdapterPosition
            if (pos != RecyclerView.NO_POSITION) onClick(getItem(pos)) 
        } }
        fun bind(t: TemplateEntity) {
            b.name.text = t.name
        }
    }

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<TemplateEntity>() {
            override fun areItemsTheSame(o: TemplateEntity, n: TemplateEntity) = o.id == n.id
            override fun areContentsTheSame(o: TemplateEntity, n: TemplateEntity) = o == n
        }
    }
}

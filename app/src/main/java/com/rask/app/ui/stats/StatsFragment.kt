package com.rask.app.ui.stats

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
import com.github.mikephil.charting.components.Legend
import com.github.mikephil.charting.data.BarData
import com.github.mikephil.charting.data.BarDataSet
import com.github.mikephil.charting.data.BarEntry
import com.github.mikephil.charting.data.PieData
import com.github.mikephil.charting.data.PieDataSet
import com.github.mikephil.charting.data.PieEntry
import com.github.mikephil.charting.formatter.ValueFormatter
import com.github.mikephil.charting.utils.ColorTemplate
import com.rask.app.R
import com.rask.app.databinding.FragmentStatsBinding
import com.rask.app.utils.DateUtils
import kotlinx.coroutines.launch

class StatsFragment : Fragment() {

    private var _binding: FragmentStatsBinding? = null
    private val binding get() = _binding!!

    private val vm: StatsViewModel by viewModels()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentStatsBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Range dropdown
        val presets = StatsViewModel.RangePreset.values()
        val labels = presets.map { getString(it.labelRes) }
        val adapter = ArrayAdapter(
            requireContext(),
            android.R.layout.simple_list_item_1,
            labels
        )
        binding.rangeInput.setAdapter(adapter)
        binding.rangeInput.threshold = 1
        binding.rangeInput.setText(labels[StatsViewModel.RangePreset.THIS_WEEK.ordinal], false)
        binding.rangeInput.setOnItemClickListener { _, _, position, _ ->
            vm.setPreset(presets[position])
        }

        // Charts
        setupBarChart()
        setupDonutChart()

        // Observe
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { vm.total.observe { total ->
                    binding.totalLabel.text = DateUtils.durationLabel(total)
                }}
                launch { vm.categories.observe { cats ->
                    val entries = cats.mapIndexed { i, c ->
                        BarEntry(i.toFloat(), (c.totalMillis / 3600_000f))
                    }
                    val ds = BarDataSet(entries, getString(R.string.stats_by_category)).apply {
                        setGradientColor(0x7A6420, 0xD4AF37)
                        valueTextSize = 10f
                        valueTextColor = 0xF5EEDC.toInt()
                    }
                    ds.label = ""
                    binding.barChart.data = if (entries.isNotEmpty()) BarData(ds) else null
                    binding.barChart.xAxis.valueFormatter = object : ValueFormatter() {
                        override fun getFormattedValue(value: Float): String {
                            val idx = value.toInt()
                            return cats.getOrNull(idx)?.label?.take(8).orEmpty()
                        }
                    }
                    binding.barChart.invalidate()
                }}
                launch { vm.tags.observe { tags ->
                    val entries = tags.take(8).map { t ->
                        PieEntry((t.totalMillis / 3600_000f), t.label.ifBlank { "—" })
                    }
                    val ds = PieDataSet(entries, "").apply {
                        colors = listOf(0xD4AF37, 0xC9A84C, 0xE6C66E, 0x7A6420, 0xA8C686, 0x9FB8D4, 0xE0B040, 0x7A7A82)
                        valueTextSize = 11f
                        valueTextColor = 0x0A0A0B.toInt()
                        sliceSpace = 2f
                    }
                    binding.donutChart.data = if (entries.isNotEmpty()) PieData(ds) else null
                    binding.donutChart.invalidate()
                }}
                launch { vm.daily.observe { days -> binding.heatmap.setData(days) }}
                launch { vm.weeklyAvg.observe { avg ->
                    binding.weeklyAvg.text = DateUtils.durationLabel(avg)
                }}
                launch { vm.bestDay.observe { best ->
                    binding.bestDay.text = best?.let {
                        "${DateUtils.parseDayBucket(it.day)} · ${DateUtils.durationLabel(it.totalMillis)}"
                    } ?: "—"
                }}
                launch { vm.peakHour.observe { peak ->
                    binding.peakHour.text = peak?.let { "${it.hour.toString().padStart(2, '0')}:00" } ?: "—"
                }}
                launch { vm.total.observe { total ->
                    val prevMonthTotal = total // simplification — actual growth calc would need a second query
                    binding.monthlyGrowth.text = "—" // placeholder for clarity
                }}
            }
        }

        // Export
        binding.btnExportPdf.setOnClickListener {
            viewLifecycleOwner.lifecycleScope.launch {
                val path = StatsExporter.exportPdf(requireContext())
                showExportResult(path)
            }
        }
        binding.btnExportCsv.setOnClickListener {
            viewLifecycleOwner.lifecycleScope.launch {
                val path = StatsExporter.exportCsv(requireContext())
                showExportResult(path)
            }
        }
    }

    private fun setupBarChart() {
        binding.barChart.apply {
            description.isEnabled = false
            legend.isEnabled = false
            axisLeft.textColor = 0x7A7A82.toInt()
            axisRight.isEnabled = false
            xAxis.textColor = 0x7A7A82.toInt()
            xAxis.setDrawGridLines(false)
            xAxis.labelRotationAngle = -30f
            setNoDataText(getString(R.string.stats_no_data))
            setNoDataTextColor(0x7A7A82.toInt())
            setDrawGridBackground(false)
            setDrawBorders(false)
            setBackgroundColor(0x00000000)
        }
    }

    private fun setupDonutChart() {
        binding.donutChart.apply {
            description.isEnabled = false
            legend.isEnabled = true
            legend.textColor = 0xB8B8BD.toInt()
            legend.textSize = 10f
            legend.horizontalAlignment = Legend.LegendHorizontalAlignment.CENTER
            isDrawHoleEnabled = true
            holeRadius = 60f
            transparentCircleRadius = 65f
            setHoleColor(0x00000000)
            setNoDataText(getString(R.string.stats_no_data))
            setNoDataTextColor(0x7A7A82.toInt())
            setUsePercentValues(false)
            setEntryLabelTextSize(10f)
            setEntryLabelColor(0x0A0A0B.toInt())
        }
    }

    private fun showExportResult(path: String?) {
        val msg = if (path != null)
            getString(R.string.stats_export_success, path)
        else
            getString(R.string.stats_export_failed)
        com.google.android.material.snackbar.Snackbar.make(
            binding.root, msg, com.google.android.material.snackbar.Snackbar.LENGTH_LONG
        ).show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}

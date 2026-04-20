<template>
  <div class="num-ball-row" :data-size="size">
    <span
      v-for="n in front"
      :key="`f-${n}`"
      class="num-ball front"
      :class="{ hit: hitFront.includes(n) }"
    >
      {{ pad(n) }}
    </span>
    <span v-if="back && back.length" class="num-ball-divider" />
    <span
      v-for="n in back"
      :key="`b-${n}`"
      class="num-ball back"
      :class="{ hit: hitBack.includes(n) }"
    >
      {{ pad(n) }}
    </span>
  </div>
</template>

<script setup>
/**
 * 号码球展示组件
 * @prop {number[]} front 前区号码
 * @prop {number[]} back  后区号码
 * @prop {number[]} hitFront 需要高亮为"命中"的前区号码
 * @prop {number[]} hitBack  需要高亮为"命中"的后区号码
 * @prop {('xs'|'sm'|'md'|'lg')} size 尺寸
 */
defineProps({
  front: { type: Array, default: () => [] },
  back: { type: Array, default: () => [] },
  hitFront: { type: Array, default: () => [] },
  hitBack: { type: Array, default: () => [] },
  size: { type: String, default: "md" },
});

function pad(n) {
  return String(n).padStart(2, "0");
}
</script>

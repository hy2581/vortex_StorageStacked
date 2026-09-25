CONFIG ?= ../config.json
OUT ?= ../result/build
.PHONY: all
all:
	bash "$(SDK)/../runtime/compile.sh" --config "$(CONFIG)" --output "$(OUT)" --model-header "$(MODEL_HEADER)" $(SOURCES)

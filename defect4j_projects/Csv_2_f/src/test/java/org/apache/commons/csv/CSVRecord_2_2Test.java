package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Field;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_2_2Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;

    @BeforeEach
    void setUp() {
        values = new String[] { "value0", "value1", "value2" };
        mapping = Collections.emptyMap();

        csvRecord = new CSVRecord(values, mapping, null, 1L);
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_ValidIndex() {
        assertEquals("value0", csvRecord.get(0));
        assertEquals("value1", csvRecord.get(1));
        assertEquals("value2", csvRecord.get(2));
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_IndexOutOfBounds() throws Exception {
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier (Java 8+)
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~java.lang.reflect.Modifier.FINAL);

        valuesField.set(csvRecord, new String[] { "a", "b" });

        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(-1));
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(2));
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_EmptyValuesArray() throws Exception {
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier (Java 8+)
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~java.lang.reflect.Modifier.FINAL);

        valuesField.set(csvRecord, new String[0]);

        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(0));
    }
}
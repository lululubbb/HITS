package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_11_4Test {

    private Constructor<CSVRecord> constructor;

    @BeforeEach
    public void setUp() throws Exception {
        constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
    }

    @Test
    @Timeout(8000)
    public void testSize_withNonEmptyValues() throws Exception {
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 1L;

        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        assertEquals(3, record.size());
    }

    @Test
    @Timeout(8000)
    public void testSize_withEmptyValues() throws Exception {
        String[] values = new String[0];
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 2L;

        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        assertEquals(0, record.size());
    }

    @Test
    @Timeout(8000)
    public void testSize_withNullValuesFieldUsingReflection() throws Exception {
        // Create instance with non-empty array first
        String[] values = new String[] {"x"};
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 3L;

        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        // Use reflection to set private final values field to null to test behavior
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier to allow modification
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~Modifier.FINAL);

        valuesField.set(record, null);

        // Calling size() should throw NullPointerException as values is null
        try {
            record.size();
        } catch (NullPointerException e) {
            // expected
            return;
        }
        throw new AssertionError("Expected NullPointerException when values is null");
    }
}